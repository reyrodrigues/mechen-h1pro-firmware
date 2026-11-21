# MECHEN H1-Pro custom firmware

Improved firmware for the **MECHEN H1-Pro (model T04)** 4" Android MP3 player (MediaTek MT6750, Android 9).

Compared with the stock firmware:

- **More secure kernel.** Years of upstream Linux, Android and MediaTek security fixes are applied, and the kernel config is hardened.
- **Remote lock removed.** The stock system ships an app that lets a remote server disable the player. It is removed, along with factory test tools and the network location services.
- **Faster, cleaner boot.** The "Orange State" warning and its 5-second wait are gone.

Everything else works as on stock: display, touch, audio (speaker and headphones), FM radio, Bluetooth, Wi-Fi, SD cards (including exFAT), sleep and charging.

> **Use at your own risk.** Flashing firmware can brick a device. Unlocking the bootloader **erases all data** on the player. Only the kernel is provided prebuilt; the system and bootloader changes are scripts you run on your own copy of the stock firmware, because those images are MECHEN's code.

## What you need

- A computer with `adb` and `fastboot` ([Android platform tools](https://developer.android.com/tools/releases/platform-tools)) and Python 3.
- For the system and bootloader steps: `e2fsprogs` (`brew install e2fsprogs` on macOS, `apt install e2fsprogs` on Linux) and the stock MECHEN firmware package for the H1-Pro.
- Strongly recommended: a full backup made with [mtkclient](https://github.com/bkerler/mtkclient) before you change anything. It is the only way back if something goes wrong.

## 1. Unlock the bootloader (erases the player)

1. On the player, enable Developer options (tap Build number 7 times) and turn on **OEM unlocking** and **USB debugging**.
2. Connect it and run:
   ```sh
   adb reboot bootloader
   fastboot flashing unlock
   ```
3. Confirm with **Volume Up** on the player, then `fastboot reboot`. The first boot after the wipe can take about 5 minutes.

To get into fastboot later without adb: power off, hold **Volume Up** while powering on, and choose **Fastboot** in the menu.

## 2. Flash the kernel

Download `boot.img` from the [latest release](../../releases/latest), check its SHA-256 against the release notes, then:

```sh
adb reboot bootloader
fastboot flash boot boot.img
fastboot reboot
```

## 3. Remove the remote lock and bloat (system)

Use `system.img` from the stock firmware package (`T04_50_2_16_4inch_M404_ST7701S_sh1282G003_MECHEN_20260331`). If your player has received a newer update than that package, use the `system` partition from your mtkclient backup instead, so system matches the rest of your firmware.

```sh
python3 kernel/tools/firmware/simg2img.py system.img system-raw.img      # sparse -> raw (skip if already raw)
python3 kernel/tools/firmware/system-debloat.py system-raw.img system-clean.img
adb reboot bootloader
fastboot flash system system-clean.img
fastboot reboot
```

## 4. Remove the Orange State warning (bootloader, optional)

Use `lk.img` from the stock package, or the `lk` partition from your backup. The script only accepts known stock files and checks every byte it changes. (Tested on hardware with the newer LK build from a device backup; the package build contains the identical routine.)

```sh
python3 kernel/tools/firmware/lk-no-orange.py lk.img lk-no-orange.bin
adb reboot bootloader
fastboot flash lk lk-no-orange.bin
fastboot reboot
```

## Going back to stock

Flash the stock images from the firmware package (or your backup) the same way: `fastboot flash boot boot.img`, `fastboot flash system system.img`, `fastboot flash lk lk.bin`.

If the player won't reach fastboot, it can still be recovered from your mtkclient backup: hold **Volume Down** while plugging in USB to enter download mode.

## Building from source

See [`kernel/BUILDING.md`](kernel/BUILDING.md). The kernel builds in Docker from a pinned source checkout plus the patches in `kernel/harness/`.

## License

GPL-2.0, see [`LICENSE`](LICENSE). This project is not affiliated with MECHEN or MediaTek.
