# Security backport tracker

Plan and process: `../FIRMWARE_REVERSE_ENGINEERING.md` → M9. Baseline: Linux 3.18.119 (MTK alps P), Android security patch level 2021-02-05 (framework; the kernel's effective level is older).

Rule: every series must keep `out/modversions.txt` all OK (vendor Wi-Fi/BT/FM/GPS modules) and pass a `fastboot boot` test before it is kept.

## Series status

| Series | Source | Patches | Status |
|---|---|---|---|
| 1 | linux-3.18.y stable v3.18.120 … v3.18.140 | `1xxx` | not started (blocked on first device boot) |
| 2 | AOSP `kernel/common` `android-3.18` (fixes not in 3.18.140) | | not started |
| 3 | Android Security Bulletins 2019-06 → present, kernel CVEs | | not started |
| 4 | MediaTek product security bulletins (MT6750/MT6755) | | not started |
| 5 | Config hardening | `config.fragment` | not started |

## CVE log

| CVE | Component | Affects this tree? | Fix source | Patch | ABI impact | Status |
|---|---|---|---|---|---|---|
| | | | | | | |

## Known unfixable (vendor binaries)

- Vendor kernel modules (`wmt_drv`, `wlan_drv_gen2`, `bt_drv`, `fmradio_drv`, `gps_drv`, `wmt_chrdev_wifi`): no source.
- TEE, modem (md1/md3), preloader/LK: proprietary, signed by the ODM chain.
