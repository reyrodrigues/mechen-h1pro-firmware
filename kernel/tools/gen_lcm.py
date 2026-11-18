#!/usr/bin/env python3
"""Regenerate the MECHEN H1-Pro LCM (panel) drivers from the stock kernel Image.

Everything here was recovered from the stock 3.18.119 kernel (base 0xffffffc000080000):
  - init/suspend tables: LCM_setting_table {u8 cmd; u8 count; u8 para[64]} (66 bytes),
    REGFLAG_DELAY = 0xFC, REGFLAG_END_OF_TABLE = 0xFD  (from lcm_init/lcm_suspend loops)
  - lcm_get_params values: decompiled stores, field names resolved with offsetof() on this tree's lcm_drv.h
  - reset/delay sequences and compare_id (reads reg 0xA1, 2 bytes, match == 0x8802)

Usage: gen_lcm.py <stock kernel Image> <kernel tree>/drivers/misc/mediatek/lcm
"""
import os, struct, sys

BASE = 0xffffffc000080000
ENTRY = 66

PANELS = {
    'st7701boe': dict(
        init=(0xffffffc001063080, 0xffffffc001063bd8),
        suspend=(0xffffffc001063bd8, 0xffffffc001063c9e),
        reset_init=[('R', 1), ('R', 0), ('D', 6), ('R', 1), ('D', 50)],
        reset_suspend=[('R', 1), ('R', 0), ('D', 10), ('R', 1), ('D', 60)],
        params='''\
	params->dsi.mode = SYNC_PULSE_VDO_MODE;
	params->dsi.vertical_backporch = 16;
	params->dsi.vertical_frontporch = 20;
	params->dsi.horizontal_sync_active = 10;
	params->dsi.horizontal_backporch = 60;
	params->dsi.horizontal_frontporch = 60;
	params->dsi.esd_check_enable = 1;
	params->dsi.customization_esd_check_enable = 1;
	params->dsi.lcm_esd_check_table[0].cmd = 0x0a;
	params->dsi.lcm_esd_check_table[0].count = 1;
	params->dsi.lcm_esd_check_table[0].para_list[0] = 0x9c;
'''),
    'nv3049f': dict(
        init=(0xffffffc001063d98, 0xffffffc001066af8),
        suspend=(0xffffffc001066af8, 0xffffffc001066bbe),
        reset_init=[('R', 1), ('D', 10), ('R', 0), ('D', 10), ('R', 1), ('D', 10)],
        reset_suspend=[('R', 1), ('R', 0), ('D', 10), ('R', 1), ('D', 10)],
        params='''\
	params->dsi.mode = SYNC_EVENT_VDO_MODE;
	params->dsi.vertical_backporch = 10;
	params->dsi.vertical_frontporch = 16;
	params->dsi.horizontal_sync_active = 4;
	params->dsi.horizontal_backporch = 44;
	params->dsi.horizontal_frontporch = 46;
	params->dsi.cont_clock = 1;
'''),
}

COMMON_PARAMS = '''\
	memset(params, 0, sizeof(LCM_PARAMS));
	params->type = LCM_TYPE_DSI;
	params->width = FRAME_WIDTH;
	params->height = FRAME_HEIGHT;
	params->dsi.LANE_NUM = LCM_TWO_LANE;
	params->dsi.data_format.format = LCM_DSI_FORMAT_RGB888;
	params->dsi.intermediat_buffer_num = 2;
	params->dsi.PS = LCM_PACKED_PS_24BIT_RGB888;
	params->dsi.packet_size = 256;
	params->dsi.vertical_sync_active = 4;
	params->dsi.vertical_active_line = FRAME_HEIGHT;
	params->dsi.horizontal_active_pixel = FRAME_WIDTH;
	params->dsi.PLL_CLOCK = 185;
'''


def table(img, start, end, name):
    assert (end - start) % ENTRY == 0, name
    rows = []
    for va in range(start, end, ENTRY):
        e = img[va - BASE: va - BASE + ENTRY]
        cmd, cnt = e[0], e[1]
        if cmd == 0xFC:
            rows.append(f'\t{{REGFLAG_DELAY, {cnt}, {{}} }},')
        elif cmd == 0xFD:
            rows.append('\t{REGFLAG_END_OF_TABLE, 0x00, {} },')
        else:
            assert cnt <= 64, (name, hex(va), cnt)
            p = ', '.join(f'0x{b:02X}' for b in e[2:2 + cnt])
            rows.append(f'\t{{0x{cmd:02X}, {cnt}, {{{p}}} }},')
    return f'static struct LCM_setting_table {name}[] = {{\n' + '\n'.join(rows) + '\n};\n'


def seq(steps):
    return ''.join(f'\tSET_RESET_PIN({v});\n' if k == 'R' else f'\tMDELAY({v});\n' for k, v in steps)


def gen(img, name, p):
    init = table(img, *p['init'], 'lcm_initialization_setting')
    susp = table(img, *p['suspend'], 'lcm_suspend_setting')
    return f'''/*
 * {name} 480x800 MIPI-DSI video panel, MECHEN H1-Pro (MT6750 / k50v1_64_bsp).
 *
 * Recovered from the stock kernel by kernel/tools/gen_lcm.py: init/suspend tables are
 * byte-exact copies of the stock tables; timings and sequences mirror the stock code.
 * Do not hand-edit tables; regenerate instead.
 */
#include <linux/string.h>
#include <linux/kernel.h>
#include "lcm_drv.h"

#define FRAME_WIDTH		(480)
#define FRAME_HEIGHT		(800)
#define LCM_ID			(0x8802)

#define REGFLAG_DELAY		0xFC
#define REGFLAG_END_OF_TABLE	0xFD

static LCM_UTIL_FUNCS lcm_util;

#define SET_RESET_PIN(v)	(lcm_util.set_reset_pin((v)))
#define MDELAY(n)		(lcm_util.mdelay(n))
#define dsi_set_cmdq(pdata, queue_size, force_update) \\
	lcm_util.dsi_set_cmdq(pdata, queue_size, force_update)
#define dsi_set_cmdq_V2(cmd, count, ppara, force_update) \\
	lcm_util.dsi_set_cmdq_V2(cmd, count, ppara, force_update)
#define read_reg_v2(cmd, buffer, buffer_size) \\
	lcm_util.dsi_dcs_read_lcm_reg_v2(cmd, buffer, buffer_size)

struct LCM_setting_table {{
	unsigned char cmd;
	unsigned char count;
	unsigned char para_list[64];
}};

{init}
{susp}
static void push_table(struct LCM_setting_table *table, unsigned int count, unsigned char force_update)
{{
	unsigned int i;

	for (i = 0; i < count; i++) {{
		unsigned char cmd = table[i].cmd;

		switch (cmd) {{
		case REGFLAG_DELAY:
			MDELAY(table[i].count);
			break;
		case REGFLAG_END_OF_TABLE:
			break;
		default:
			dsi_set_cmdq_V2(cmd, table[i].count, table[i].para_list, force_update);
		}}
	}}
}}

static void lcm_set_util_funcs(const LCM_UTIL_FUNCS *util)
{{
	memcpy(&lcm_util, util, sizeof(LCM_UTIL_FUNCS));
}}

static void lcm_get_params(LCM_PARAMS *params)
{{
{COMMON_PARAMS}{p['params']}}}

static void lcm_init(void)
{{
{seq(p['reset_init'])}	push_table(lcm_initialization_setting,
		   sizeof(lcm_initialization_setting) / sizeof(struct LCM_setting_table), 1);
}}

static void lcm_suspend(void)
{{
{seq(p['reset_suspend'])}	push_table(lcm_suspend_setting,
		   sizeof(lcm_suspend_setting) / sizeof(struct LCM_setting_table), 1);
}}

static void lcm_resume(void)
{{
	lcm_init();
}}

static unsigned int lcm_compare_id(void)
{{
	unsigned int id, array[4];
	unsigned char buffer[2];

	SET_RESET_PIN(1);
	SET_RESET_PIN(0);
	MDELAY(10);
	SET_RESET_PIN(1);
	MDELAY(200);

	array[0] = 0x00023700;	/* max return packet size: 2 */
	dsi_set_cmdq(array, 1, 1);
	read_reg_v2(0xA1, buffer, 2);
	id = (buffer[0] << 8) | buffer[1];
	pr_debug("{name} id = 0x%x\\n", id);
	return (id == LCM_ID) ? 1 : 0;
}}

LCM_DRIVER {name}_lcm_drv = {{
	.name = "{name}",
	.set_util_funcs = lcm_set_util_funcs,
	.get_params = lcm_get_params,
	.init = lcm_init,
	.suspend = lcm_suspend,
	.resume = lcm_resume,
	.compare_id = lcm_compare_id,
}};
'''


def main():
    img = open(sys.argv[1], 'rb').read()
    lcmdir = sys.argv[2]
    for name, p in PANELS.items():
        d = os.path.join(lcmdir, name)
        os.makedirs(d, exist_ok=True)
        open(os.path.join(d, f'{name}.c'), 'w').write(gen(img, name, p))
        open(os.path.join(d, 'Makefile'), 'w').write(
            f'obj-y += {name}.o\n\nccflags-$(CONFIG_MTK_LCM) += -I$(srctree)/drivers/misc/mediatek/lcm/inc\n')
        print(f'{name}: written')


if __name__ == '__main__':
    main()
