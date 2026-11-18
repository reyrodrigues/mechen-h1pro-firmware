/*
 * Hynitron CST3XX touch driver for the MECHEN H1-Pro (MT6750, kernel 3.18, MTK tpd framework).
 *
 * Clean-room reimplementation of the stock "Hynitron_MTK_CST3XX_Driver_V1.2_20190717" behaviour,
 * recovered from the stock kernel (cst3xx_tpd_probe, cst3xx_touch_handler, cst3xx_suspend,
 * cst3xx_resume, cst3xx_local_init, cst3xx_ts_init, hyn_reset_proc).
 *
 * Deliberately NOT included: touch-IC firmware update (stock only offered it via proc/sysfs from a
 * user-supplied file; it was never run at boot), proc/sysfs debug tooling, proximity, gestures.
 * The driver therefore never writes the controller's flash.
 *
 * Protocol (all via register 0xD0xx, I2C address 0x5a):
 *   read 0xD000, 7 bytes : point0[5], info, 0xAB
 *       info == 0x80            -> touch-key event only
 *       info & 0x7f == n (<6)   -> n fingers; n > 1: read the remaining (n-1)*5 (+2 key bytes if
 *                                  info & 0x80) bytes + 0xAB marker from 0xD007, <= 6 bytes per read
 *   point: b0 = id<<4 | status<<1 (status 3 = down), X = b1<<4 | b3>>4, Y = b2<<4 | (b3 & 0xf),
 *          size = b4 >> 1
 *   ack: write D0 00 AB.  Commands: D1 06 = normal mode, D1 05 = sleep, D1 0E = pre-reset.
 */
#include <linux/delay.h>
#include <linux/gpio.h>
#include <linux/i2c.h>
#include <linux/input.h>
#include <linux/interrupt.h>
#include <linux/kthread.h>
#include <linux/of.h>
#include <linux/of_irq.h>
#include <linux/regulator/consumer.h>
#include <linux/sched.h>
#include <linux/wait.h>
#include "tpd.h"

#define CST3XX_DRIVER_VERSION	"MP3 clean-room of Hynitron_MTK_CST3XX_Driver_V1.2_20190717"
#define CST3XX_I2C_ADDR		0x5a
#define CST3XX_MAX_POINTS	5
#define CST3XX_RST_PIN		0

static struct i2c_client *cst3xx_client;
static struct task_struct *cst3xx_thread;
static DECLARE_WAIT_QUEUE_HEAD(cst3xx_waiter);
static int cst3xx_irq_flag;
static unsigned int cst3xx_irq;
static int cst3xx_key_index = 0xff;	/* currently pressed touch key, 0xff = none */
static int cst3xx_key_down;

static const unsigned short cst3xx_keys[] = { KEY_BACK, KEY_HOMEPAGE, KEY_MENU };	/* stock table */

static int cst3xx_send2(u8 a, u8 b, int tries)
{
	u8 buf[2] = { a, b };
	int i;

	for (i = 0; i < tries; i++) {
		if (i2c_master_send(cst3xx_client, buf, 2) > 0 ||
		    i2c_master_send(cst3xx_client, buf, 2) > 0)
			return 0;
		mdelay(2);
	}
	return -EIO;
}

/* buf[0..1] = register, response overwrites buf (stock cst3xx_i2c_read_register) */
static int cst3xx_read_reg(u8 *buf, int len)
{
	if (i2c_master_send(cst3xx_client, buf, 2) < 1 && i2c_master_send(cst3xx_client, buf, 2) < 1)
		return -EIO;
	if (i2c_master_recv(cst3xx_client, buf, len) < 1 && i2c_master_recv(cst3xx_client, buf, len) < 1)
		return -EIO;
	return 0;
}

static void cst3xx_hw_reset(unsigned int settle_ms)
{
	tpd_gpio_output(CST3XX_RST_PIN, 0);
	mdelay(20);
	tpd_gpio_output(CST3XX_RST_PIN, 1);
	mdelay(settle_ms);
}

/* acknowledge the frame; on repeated failure reset the controller like stock */
static void cst3xx_ack(void)
{
	u8 ack[3] = { 0xd0, 0x00, 0xab };

	if (i2c_master_send(cst3xx_client, ack, 3) > 0 || i2c_master_send(cst3xx_client, ack, 3) > 0)
		return;
	cst3xx_send2(0xd1, 0x0e, 1);
	cst3xx_hw_reset(20);
}

static void cst3xx_release_all(struct input_dev *dev)
{
	input_report_key(dev, BTN_TOUCH, 0);
	input_mt_sync(dev);
	input_sync(dev);
}

/* read len bytes starting at 0xD007 into dst, max 6 bytes per transfer (MTK I2C FIFO) */
static int cst3xx_read_tail(u8 *dst, int len)
{
	int off = 0;

	while (off < len) {
		u8 buf[6];
		int n = min(len - off, 6);

		buf[0] = 0xd0;
		buf[1] = 7 + off;
		if (cst3xx_read_reg(buf, n))
			return -EIO;
		memcpy(dst + off, buf, n);
		off += n;
	}
	return 0;
}

static void cst3xx_report_keys(struct input_dev *dev, u8 b0, u8 b1)
{
	int idx = (b1 >> 4) - 1;

	if (!(b0 & 0x80) || idx < 0 || idx >= ARRAY_SIZE(cst3xx_keys))
		return;
	if ((b0 & 0x7f) == 3) {
		if (idx == cst3xx_key_index || cst3xx_key_index == 0xff) {
			input_report_key(dev, cst3xx_keys[idx], 1);
			cst3xx_key_index = idx;
			cst3xx_key_down = 1;
		} else {
			input_report_key(dev, cst3xx_keys[cst3xx_key_index], 0);
			cst3xx_key_index = 0xff;
		}
	} else {
		input_report_key(dev, cst3xx_keys[idx], 0);
		input_report_key(dev, BTN_TOUCH, 0);
		input_mt_sync(dev);
		cst3xx_key_down = 0;
		cst3xx_key_index = 0xff;
	}
}

static void cst3xx_handle_frame(struct input_dev *dev)
{
	u8 data[CST3XX_MAX_POINTS * 5 + 4];
	u8 buf[7] = { 0xd0, 0x00 };
	int n, i, down = 0, up = 0, have_keys;

	if (cst3xx_read_reg(buf, 7) || buf[6] != 0xab)
		goto ack_only;

	if (buf[5] == 0x80) {			/* touch key only */
		cst3xx_ack();
		cst3xx_report_keys(dev, buf[0], buf[1]);
		input_sync(dev);
		return;
	}

	n = buf[5] & 0x7f;
	if (n >= 6)
		goto ack_only;
	if (n == 0) {
		cst3xx_release_all(dev);
		goto ack_only;
	}

	memcpy(data, buf, 5);
	have_keys = buf[5] & 0x80;
	if (n > 1) {
		int tail = (n - 1) * 5 + (have_keys ? 3 : 1);

		if (cst3xx_read_tail(data + 5, tail) || data[5 + tail - 1] != 0xab)
			goto ack_only;
	}
	cst3xx_ack();

	for (i = 0; i < n; i++) {
		const u8 *p = data + i * 5;

		if (((p[0] >> 1) & 7) == 3) {
			input_report_key(dev, BTN_TOUCH, 1);
			input_report_abs(dev, ABS_MT_POSITION_X, (p[1] << 4) | (p[3] >> 4));
			input_report_abs(dev, ABS_MT_POSITION_Y, (p[2] << 4) | (p[3] & 0xf));
			input_report_abs(dev, ABS_MT_TOUCH_MAJOR, p[4] >> 1);
			input_report_abs(dev, ABS_MT_WIDTH_MAJOR, p[4] >> 1);
			input_report_abs(dev, ABS_MT_TRACKING_ID, p[0] >> 4);
			input_mt_sync(dev);
			down++;
		} else {
			up++;
		}
	}
	if (!down && up) {
		input_report_key(dev, BTN_TOUCH, 0);
		input_mt_sync(dev);
	}
	if (n > 1 && have_keys && cst3xx_key_down)
		cst3xx_report_keys(dev, data[(n - 1) * 5 + 5], data[(n - 1) * 5 + 6]);
	input_sync(dev);
	return;

ack_only:
	cst3xx_ack();
}

static int cst3xx_touch_thread(void *unused)
{
	struct sched_param param = { .sched_priority = 4 };

	sched_setscheduler(current, SCHED_RR, &param);
	while (!kthread_should_stop()) {
		wait_event_interruptible(cst3xx_waiter, cst3xx_irq_flag || kthread_should_stop());
		cst3xx_irq_flag = 0;
		if (kthread_should_stop())
			break;
		cst3xx_handle_frame(tpd->dev);
	}
	return 0;
}

static irqreturn_t cst3xx_irq_handler(int irq, void *dev_id)
{
	cst3xx_irq_flag = 1;
	wake_up_interruptible(&cst3xx_waiter);
	return IRQ_HANDLED;
}

static int cst3xx_irq_registration(void)
{
	struct device_node *node = of_find_matching_node(NULL, touch_of_match);
	u32 ints[2] = { 0, 0 };

	if (!node)
		return -ENODEV;
	of_property_read_u32_array(node, "debounce", ints, ARRAY_SIZE(ints));
	gpiod_set_debounce(gpio_to_desc(ints[0]), ints[1]);
	cst3xx_irq = irq_of_parse_and_map(node, 0);
	if (!cst3xx_irq)
		return -EINVAL;
	return request_irq(cst3xx_irq, cst3xx_irq_handler, IRQF_TRIGGER_RISING,
			   "TOUCH_PANEL-eint_cst3xx", NULL);
}

static int cst3xx_tpd_probe(struct i2c_client *client, const struct i2c_device_id *id)
{
	int ret, i;

	pr_info("[HYN] probe, %s\n", CST3XX_DRIVER_VERSION);
	if (client->addr != CST3XX_I2C_ADDR)
		client->addr = CST3XX_I2C_ADDR;	/* stock: DT says 0x5d, chip answers at 0x5a */
	cst3xx_client = client;

	tpd_gpio_output(CST3XX_RST_PIN, 0);
	mdelay(100);
	tpd->reg = regulator_get(tpd->tpd_dev, "vtouch");
	if (IS_ERR(tpd->reg))
		return PTR_ERR(tpd->reg);
	ret = regulator_set_voltage(tpd->reg, 2800000, 2800000);
	if (ret)
		return ret;
	if (regulator_enable(tpd->reg))
		pr_err("[HYN] vtouch enable failed\n");
	mdelay(100);
	tpd_gpio_output(CST3XX_RST_PIN, 1);
	tpd_gpio_as_int(1);
	mdelay(400);

	cst3xx_send2(0xd1, 0x06, 5);		/* normal mode */
	cst3xx_hw_reset(200);			/* stock hyn_reset_proc(200) */

	tpd_gpio_as_int(1);
	ret = cst3xx_irq_registration();
	if (ret)
		pr_err("[HYN] irq registration failed: %d\n", ret);

	tpd_load_status = 1;
	disable_irq(cst3xx_irq);
	cst3xx_thread = kthread_run(cst3xx_touch_thread, NULL, "Hyn_device");
	if (IS_ERR(cst3xx_thread))
		pr_err("[HYN] thread create failed\n");
	enable_irq(cst3xx_irq);

	for (i = 0; i < ARRAY_SIZE(cst3xx_keys); i++)
		input_set_capability(tpd->dev, EV_KEY, cst3xx_keys[i]);
	return 0;
}

static int cst3xx_tpd_remove(struct i2c_client *client)
{
	return 0;
}

static const struct of_device_id cst3xx_dt_match[] = {
	{ .compatible = "mediatek,cap_touch_cst" },
	{ .compatible = "mediatek,cap_touch" },
	{},
};

static const struct i2c_device_id cst3xx_id[] = { { "Hyn_device", 0 }, {} };

static struct i2c_driver cst3xx_i2c_driver = {
	.driver = {
		.name = "Hyn_device",
		.of_match_table = cst3xx_dt_match,
	},
	.probe = cst3xx_tpd_probe,
	.remove = cst3xx_tpd_remove,
	.id_table = cst3xx_id,
};

static void cst3xx_suspend(struct device *h)
{
	disable_irq(cst3xx_irq);
	cst3xx_release_all(tpd->dev);
	cst3xx_send2(0xd1, 0x05, 5);		/* sleep */
}

static void cst3xx_resume(struct device *h)
{
	cst3xx_release_all(tpd->dev);
	cst3xx_send2(0xd1, 0x0e, 1);
	tpd_gpio_output(CST3XX_RST_PIN, 0);
	mdelay(20);
	tpd_gpio_output(CST3XX_RST_PIN, 1);
	mdelay(30);
	cst3xx_send2(0xd1, 0x06, 1);
	enable_irq(cst3xx_irq);
}

static int cst3xx_local_init(void)
{
	if (i2c_add_driver(&cst3xx_i2c_driver)) {
		pr_err("[HYN] unable to add i2c driver\n");
		return -1;
	}
	if (tpd_load_status == 0) {
		i2c_del_driver(&cst3xx_i2c_driver);
		return -1;
	}
	input_set_abs_params(tpd->dev, ABS_MT_TRACKING_ID, 0, 6, 0, 0);
	if (tpd_dts_data.use_tpd_button)
		tpd_button_setting(tpd_dts_data.tpd_key_num, tpd_dts_data.tpd_key_local,
				   tpd_dts_data.tpd_key_dim_local);
	tpd_type_cap = 1;
	tpd->dev->id.vendor = 0;
	return 0;
}

static struct tpd_driver_t cst3xx_tpd_driver = {
	.tpd_device_name = "cst3xx",
	.tpd_local_init = cst3xx_local_init,
	.suspend = cst3xx_suspend,
	.resume = cst3xx_resume,
	.tpd_have_button = 0,
};

static int __init cst3xx_ts_init(void)
{
	pr_info("[HYN] %s\n", CST3XX_DRIVER_VERSION);
	tpd_get_dts_info();
	if (tpd_driver_add(&cst3xx_tpd_driver) < 0)
		pr_err("[HYN] add cst3xx driver failed\n");
	return 0;
}

static void __exit cst3xx_ts_exit(void)
{
	tpd_driver_remove(&cst3xx_tpd_driver);
}

module_init(cst3xx_ts_init);
module_exit(cst3xx_ts_exit);
MODULE_LICENSE("GPL");
MODULE_DESCRIPTION("Hynitron CST3XX touch (MECHEN H1-Pro, recovered from stock behaviour)");
