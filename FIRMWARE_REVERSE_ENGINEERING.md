# Firmware Reverse Engineering — Next Steps

Companion to `FIRMWARE_ANALYSIS.md` (findings & feasibility). This document is the working plan: what happens next, in what order, with commands, success criteria, and rollback notes. Update the checkboxes as we go.

Status: 2026-11-18 · Device: MECHEN H1-Pro (T04) · MT6750 / k50v1_64_bsp · Android 9 · Linux 3.18.119

---

## Where we are

All offline analysis of the firmware package is complete (details in `FIRMWARE_ANALYSIS.md`):

- Firmware unpacked: boot/recovery images, recovery ramdisk, kernel Image, base DTB, exact kernel `.config`
- system/vendor converted to raw ext4 and readable (`_analysis/system_raw.img`, `vendor_raw.img`)
- Kernel symbolized: `_analysis/kernel_with_symbols_fixed.elf` (46,135 symbols, base `0xffffffc000080000`)
- App layer audited: launcher = `MtkLauncher3`, music = `MusicBspPlus`; threats identified (`SystemLock` HTTP kill-switch at `47.120.15.138:7900`, factory apps, Baidu location, spoofed BLU G90 fingerprint)
- Boot posture established: no AVB, dm-verity not enforced in normal boot, fastboot + MTK download mode available
- Feasibility answered: GSI (Android 11 LOS 18.1, arm64 A-only vanilla) viable; kernel rebuild possible **if** matching source is found

**Nothing has been flashed to the device yet. No on-device work has been done.** Device available again Friday 2026-11-20. Start with "Next session checklist" below.

The kernel build is reproducible from a fresh checkout: see `kernel/BUILDING.md` (`./setup.sh <firmware>` then `./build.sh`). The repo root is a git repository containing all generated code and docs.

## Environment status (this Mac)

| Tool | Status | Used for |
|---|---|---|
| adb / fastboot | ✅ `~/Library/Android/sdk/platform-tools/` | device comms, flashing |
| e2fsprogs (`debugfs`) | ✅ brew (keg-only: `/opt/homebrew/opt/e2fsprogs/sbin/debugfs`, not on PATH) | read/edit ext4 images |
| apktool | ✅ brew | APK de/recompile |
| vmlinux-to-elf | ✅ `_analysis/.venv` | kernel symbolization |
| unpack/repack scripts | ✅ `_analysis/*.py` | boot images, sparse images |
| `dtc` | ✅ brew 1.8.1 — base DTB decompiled to `_analysis/boot_out/appended.dts` (2,963 lines, `model = "MT6755"`, PMIC MT6351) | DTB ↔ DTS (needed for kernel/board work) |
| SP Flash Tool (macOS) or mtkclient | ❌ download when needed | full-chip backup/flash (M2) |
| Ghidra 12.2 | ✅ `ghidra_12.2_PUBLIC/` (local install, fixed for macOS) | interactive kernel RE (M7) |

Ghidra working setup (2026-11-18): official 12.2 ships **no macOS natives** — decompiler built from source for arm64 + x86_64 and installed into `Ghidra/Features/Decompiler/os/mac_{arm,x86}_64/`. Runs on standalone Temurin JDK 25 at `~/jdks/jdk-25.0.5+8` (wired via `JAVA_HOME_OVERRIDE` in `support/launch.properties`). Headless heap raised: `MAXMEM_DEFAULT=8G` in `support/analyzeHeadless` (stock 2G OOMs on this kernel; the script default overrides env vars and launch.properties VMARGS). Ready-made analyzed project: `_analysis/ghidra_proj_v3` → `KernelRE`, containing `kernel_with_symbols_fixed.elf` (correct base, non-returning-function discovery disabled).

> ⚠️ **CORRECTION (2026-11-18): `kernel_with_symbols.elf`, `ghidra_proj/KernelRE` and `_analysis/decompiled/` use the WRONG base address** (`0xffffffc000082000`; vmlinux-to-elf guessed it from `_stext`). The Image header's text_offset is 0x80000, so the true base is `0xffffffc000080000`: every symbol labels code 0x2000 bytes away. Verified: 84% of function symbols hit a prologue at the correct base vs 1% at the old one. Names-only results (M7 symbol matching) are unaffected; any reading of decompiled code from the old corpus is invalid. Fixed: `kernel_with_symbols_fixed.elf` (`--base-address ffffffc000080000`) → `ghidra_proj_v3/KernelRE` (with `NoNoReturnDiscovery`), board-driver decompiles in `decompiled_board_v3/` and `decompiled_rtc/`. The wrong-base ELF/project/corpus and the intermediate `ghidra_proj_fixed`/`decompiled_board` (truncated at printk) were deleted 2026-11-18.

**Full pseudo-C corpus:** the original 82k-function corpus was wrong-base and has been deleted. To regenerate a correct one: `support/analyzeHeadless _analysis/ghidra_proj_v3 KernelRE -process kernel_with_symbols_fixed.elf -noanalysis -scriptPath kernel/tools/ghidra -postScript DecompileAll.java <outdir> [nameRegex]`.

---

## M0 — Prep (before device work)

- [x] `brew install dtc` (2026-11-18) + decompiled `appended.dtb` → `appended.dts`
- [ ] Download SP Flash Tool (macOS) + the MT6750 USB VCOM drivers; alternatively/additionally set up `mtkclient` in Docker or a Linux VM (open-source, no vendor download-agent needed, works well on MT675x)
- [ ] Create the flash-log convention: every flash gets one line in this file (date, partition(s), image hash, result)
- [x] Ghidra: installed, macOS-fixed, kernel analyzed — see environment section above

## M1 — On-device recon (read-only, no risk)

- [ ] Enable Developer options → USB debugging (if the Settings app allows; else Volume-based boot to fastboot)
- [ ] `adb shell getprop` → record: exact resolution/density, `ro.boot.*`, lock state hints, `ro.build.fingerprint`
- [ ] `adb shell cat /proc/partitions`, `ls -l /dev/block/by-name` (or the mtk-msdc path from fstab) → confirm partition map matches the scatter
- [ ] `adb shell ls /system/priv-app /system/app` → confirm installed set matches our image
- [ ] `adb reboot bootloader` → `fastboot devices`; then `fastboot oem lks` → **record lock state**
- [ ] Identify boot-combo for download mode & recovery (typically Vol keys at power-on) and confirm SP Flash Tool / mtkclient sees the device
- [ ] Check for a UART console pad on the PCB (kernel cmdline has `console=ttyMT3,921600`); optional but valuable for un-brick debugging

**Success criteria:** confirmed partition map, fastboot visibility, known lock state, documented boot combos.

## M2 — Full backup (the gate — no modification before this)

- [ ] Read back **every** partition from the scatter via SP Flash Tool (Readback) or `mtkclient rdmp` — minimum set: `preloader`, `lk`, `lk2`, `boot`, `recovery`, `logo`, `odmdtbo`, `tee1/2`, `secro`, `seccfg`, `proinfo`, `nvram`, `nvdata`, `protect1/2`, `expdb`, `system`, `vendor`, `userdata`, `cache`
- [ ] Verify dumps (sizes vs scatter; mount/dump a file from the backed-up system image and compare hash against `_analysis/system_raw.img`)
- [ ] Copy backups to a second location (the original zip is not a substitute — it lacks nvram/nvdata/proinfo device calibration)
- [ ] Also grab `dd` copies of boot/recovery/lk over adb as a cross-check

**Note:** nvram/nvdata/proinfo hold Wi-Fi/BT calibration and unit data — losing them degrades the radio permanently. This is the single most important milestone.

## M3 — Lock state & signature enforcement test

- [ ] If locked: `fastboot flashing get_unlock_ability` → if allowed, `fastboot flashing unlock` (confirm on screen with Volume UP) — **wipes userdata; do after M2**
- [ ] SBC test: take stock `boot.img`, flip one byte of the cmdline padding (not the kernel), `fastboot flash boot` it → if it boots, signature verification is off ⇒ custom boot/lk kernels are viable. If it doesn't boot, reflash stock boot via download mode and treat SBC as ON (GSI/system-only path still open; kernel rebuild becomes moot)
- [ ] Record the result here: SBC = ____ (on/off)

## M4 — Custom firmware v1: debloated + hardened stock

Workflow: copy `_analysis/system_raw.img` → edit with `debugfs` (or loop-mount in Docker/Linux VM) → flash `system` only, one change-set per flash.

- [ ] Remove from `/system/priv-app` + `/system/app`: `SystemLock`, `EngineerMode`, `ValidationTools`, `AutoDialer`, `ATMWifiMeta`, `Baidu_Location`, `LPPeService` (+ `NlpService`/`MtkNlp` if location unused)
- [ ] Verify `MusicBspPlus` + `MtkLauncher3` unaffected; device boots; USB-MTP works
- [ ] build.prop: honest fingerprint/model fields (keep a `ro.build.fingerprint` that matches actual Android 9 / MECHEN H1-Pro identity)
- [ ] Decide GMS (open question below) and act accordingly
- [ ] Keep `sdupdate` in this build (it's our emergency update channel), revisit in v2
- [ ] Test matrix pass: boot, music playback (speaker + headset + BT), hardware keys, SD card, USB-MTP from macOS, charge UI, battery life sanity
- [ ] Rollback proof-test: reflash stock system once, confirm, re-apply v1

## M5 — Custom firmware v2: bespoke launcher

- [ ] Scaffold the launcher app (Kotlin, min/targetSdk 28, no GMS dependencies): HOME + DEFAULT intent filters, 4-inch/240dpi-first UI (large targets, dark theme, one-thumb reachability)
- [ ] Media integration: MediaStore query + Media3/ExoPlayer or MediaSession control of `MusicBspPlus`; handle hardware keys (next/prev/vol) and headset buttons
- [ ] Dev loop on-device: `adb install -r` while stock launcher still default; `adb shell cmd package set-home-activity` to trial-switch
- [ ] Bake in: `debugfs` write to `/system/priv-app/CustomLauncher/CustomLauncher.apk`, remove `MtkLauncher3` from the image
- [ ] Optional privileged permissions via `/system/etc/sysconfig/customlauncher.xml` whitelist (no platform signature needed)
- [ ] Full test-matrix pass + ship as v2 image

## M6 — Custom firmware v3: GSI experiment (optional, replaces M4/M5 base if successful)

- [ ] Source image: LineageOS 18.1 GSI, **arm64 A-only vanilla** (TrebleDroid/AndyCGYan builds)
- [ ] `fastboot flash system <gsi>.img` → wipe cache/userdata → boot
- [ ] Expected bring-up: audio/touch/USB first; then Wi-Fi/BT (expect phh-Treble app tweaks for MTK); note camera status
- [ ] Port the v2 launcher onto the GSI (plain `adb install`; no image surgery needed)
- [ ] Decide final base: debloated stock (M4/M5) vs GSI — record decision + reasons here
- [ ] Rollback path (tested): download mode → reflash stock system/vendor/boot from M2 backups

## M7 — Kernel source hunt & verification (feeds M8)

- [ ] Search GitHub for alps Android 9 MT6750 kernel dumps (`k50v1_64_bsp`, `kernel/alps`, blueshark-family firmware); check the TWRP k50v1 tree's ecosystem
- [ ] Alternative trees: MT6755 3.18 GPL releases (Sony Xperia XA, Oppo R9-era, kernel-3.18_t8p, AOSP kernel/mediatek android-3.18)
- [ ] GPL request to MECHEN sales/support (cheap to send; reference GPL § source obligations) — low expectations
- [ ] **Verification of any candidate:** build with our `.config` (GCC 4.9 aarch64) → compare symbol addresses against `_analysis/kernel_with_symbols_fixed.elf` (large overlap = right source); decompile-diff a few MTK functions if needed
- [x] Record here: source found = **base tree yes, board drivers no** (2026-11-18, see results below)

### M7 results (2026-11-18)

Method: shallow-cloned candidates; scored our 44,533 named kernel functions (`kernel_symbols.txt`, compiler suffixes stripped) against every identifier in each tree's .c/.h/.S. No build yet (needs case-sensitive FS + GCC 4.9 aarch64 → Linux VM/Docker).

| Candidate | Version | k50v1_64_bsp defconfig | Symbol match |
|---|---|---|---|
| [zhiluan233/android_kernel_cyberfurryrobot_cfb001](https://github.com/zhiluan233/android_kernel_cyberfurryrobot_cfb001) | **3.18.119** (exact) | yes (489/536 lines identical to ours) | 41,654 (93.5%) — **recommended base** |
| [suddenBook/android_kernel_xsh_k50sv1_64_bsp](https://github.com/suddenBook/android_kernel_xsh_k50sv1_64_bsp) | 3.18.140 | yes (same 489/536) | 41,716 (93.7%) — newer stable patches, LOS 17.1-maintained |
| [Vgdn1942/android_kernel_mt6755_3.18.119](https://github.com/Vgdn1942/android_kernel_mt6755_3.18.119) | 3.18.119 | no | 41,496 (93.2%) |

Of the ~2,800 unmatched names, ~2,400 are macro-generated (ftrace/perf trace events, sysfs show/store, `__pi_` aliases, erratum veneers) and not real gaps. The **genuinely missing code is the ODM board layer** (absent from all three trees):

- LCM panels: `st7701boe` + `nv3049f` (`CONFIG_CUSTOM_KERNEL_LCM="st7701boe nv3049f"`)
- Touch: Hynitron CST3XX (`Hynitron_MTK_CST3XX_Driver_V1.2_20190717`, `CONFIG_TOUCHSCREEN_MTK_CTSXXXX`)
- MP3 hardware keys: `nextsongkey_*`, `previoussongkey_*`, `contactskey_*`, `custom_key_eint_register`
- `xunhubattery` (ODM battery driver), MSA311 accelerometer, S5K3L2 camera sensor init
- exFAT driver (Samsung-style `ffs*`/`Fs*` API; not under `CONFIG_EXFAT_FS`) — needed for large SD cards; public sources exist

Next: source the Hynitron CST3XX v1.2 and exFAT drivers publicly; rewrite `st7701boe`/`nv3049f` LCM + key/battery drivers from the decompiled stock kernel (done: see session log); diff our full config against the defconfig; test-build in Linux/Docker and compare section sizes/symbol addresses.

- [x] Build harness created (2026-11-18): `kernel/` (see `kernel/README.md`). Repacker reproduces stock `boot.img` byte-identically, including the VB1.0 signature: **stock boot is signed with the public AOSP verity test key**. Generic kernel compiles; remaining failures are the board drivers listed above.

## M8 — Kernel rebuild (only if M7 yields verified source + M3 says SBC off)

- [x] Build stock-equivalent 3.18.119 (2026-11-18): `kernel/out/boot-<stamp>.img`, patches 0001–0013, all vendor modules pass ABI check
- [ ] First boot via `fastboot boot` (RAM only); then flash only after the full test matrix passes (no other changes in this flash)
- [ ] Hardening pass: `CONFIG_DEVMEM` off, `CONFIG_KALLSYMS` off, SELinux `CHECKREQPROT_VALUE=0`. **Not `CONFIG_MODULES=n`**: vendor Wi-Fi/BT/FM/GPS are loadable modules (`/vendor/lib/modules/*.ko`). Module signing can't be enforced either (the vendor modules are unsigned and can't be rebuilt), so keep `MODULES=y` and rely on SELinux (enforcing) to restrict module loading
- [ ] Security backports: see M9
- [ ] Optional features: WireGuard backport, CPU governor tuning for playback battery life
- [ ] Repack with reversed `unpack_bootimg.py` flow (gzip kernel + appended DTB, page 2048); flash `boot` only
- [ ] Keep per-build images + hashes in this file

## M9 — Security backports (after the M8 kernel boots and passes the test matrix)

Goal: bring the 3.18.119 kernel as close to "all known fixes" as practical without breaking the vendor-module ABI. Every step is one patch series, built with `./build.sh` (the modversions check must stay green) and boot-tested before the next.

**Gate before each series:** `out/modversions.txt` all OK. A fix that changes a struct used by `wmt_drv`/`wlan_drv_gen2`/`bt_drv`/`gps_drv`/`fmradio_drv`/`wmt_chrdev_wifi` breaks Wi-Fi/BT: either adapt it ABI-neutrally or skip and record.

1. **Linux 3.18 stable 3.18.119 → 3.18.140** (final 3.18.y release, 2019-05). 21 upstream releases, ~1–2k commits, from `git.kernel.org/pub/scm/linux/kernel/git/stable/linux.git` tags `v3.18.120..v3.18.140`. Approach: `git am`/cherry-pick release by release onto `mp3-build`, resolve MTK conflicts, run modversions check per release. Shortcut/reference: `suddenBook/android_kernel_xsh_k50sv1_64_bsp` is the same MTK base already at 3.18.140 (diff it to see how conflicts were resolved).
2. **Android common `android-3.18`** (`android.googlesource.com/kernel/common`, branch `android-3.18`): Android-specific security fixes (binder, ashmem, ion, etc.) beyond upstream stable, until the branch was deprecated. Cherry-pick security-relevant commits not already in 3.18.140.
3. **Android Security Bulletins 2019-06 → present (kernel component):** for each kernel CVE, check whether 3.18 is affected and the code exists in this tree; backport the upstream fix (often from 4.4/4.9 Android branches) manually. Track in `kernel/SECURITY.md` (CVE, affected?, patch #, status).
4. **MediaTek bulletins** (`corp.mediatek.com/product-security-bulletin`): MT6750/MT6755 kernel-driver CVEs (ion, m4u, ccci, wlan, connectivity). Many fixes live in vendor modules we can't rebuild: record as "unfixable without vendor source".
5. **Config hardening** (after 1–4): `CONFIG_DEVMEM=n`, `CONFIG_KALLSYMS=n` (keep for debug builds), SELinux `CHECKREQPROT_VALUE=0`, `CONFIG_SECURITY_DMESG_RESTRICT=y`, `CONFIG_SECURITY_PERF_EVENTS_RESTRICT` (if backported), `CONFIG_HARDENED_USERCOPY` (already y), `CONFIG_STRICT_DEVMEM`. Disable unused attack surface: camera/flashlight/NFC stacks, `CONFIG_USB_*` gadgets not needed for MTP/ADB.
6. Known limits: no KASLR/PAN/CFI on 3.18 arm64; vendor `.ko` and TEE/modem firmware stay as shipped.

Process per series: branch `sec/<series>` in `src/linux` → export to `harness/patches/1xxx-*.patch` (keep 0001–0013 as the board base) → `./build.sh reprepare && ./build.sh` → `fastboot boot` test → flash log entry.

## Session log

### 2026-11-18 — offline kernel bring-up (no device)

- Validated `FIRMWARE_ANALYSIS.md` against the artifacts; corrections applied (SoC naming, debuggable/first_api_level ambiguities, SBC caveat, section numbering).
- Researched GSI vs kernel vs postmarketOS (mainline MT6755 support is minimal: storage/audio missing). Installed Ghidra 12.2 locally, `dtc`.
- **M7 source hunt:** best base `zhiluan233/android_kernel_cyberfurryrobot_cfb001` @ a30c78c0 (3.18.119, `k50v1_64_bsp`, 93.5% of stock function names). Stock build root was `/home/ms06/code/mt6755/mtk6755_p_alps/ap/kernel-3.18` (MTK alps P tree).
- **Major correction:** the original symbolized ELF/Ghidra project/82k-function corpus used the wrong base (0x…82000 instead of 0x…80000). Rebuilt: `_analysis/kernel_with_symbols_fixed.elf`, `_analysis/ghidra_proj_v3` (with `NoNoReturnDiscovery`, otherwise functions are truncated at `printk`).
- Built `kernel/` harness: case-sensitive sparse volume, Docker (Ubuntu 18.04 + AOSP GCC 4.9) under colima/Rosetta, `mkbootimg.py` (byte-identical stock repack incl. VB1.0 signature; **stock boot is signed with the public AOSP verity test key**), modversions checker.
- Patches 0001–0013 (see `kernel/BUILDING.md`): tree repairs; LCM `st7701boe`/`nv3049f` (480×800, byte-exact tables); battery tables; linear-charger fixes; vendor-module ABI (rtc_time.tm_cnt, 2-callback wmt bridge, 2 CRCs pinned after verifying layout); exFAT 1.2.9; side keys (DT `mediatek,{previous,next}songkey`, `contactskey`; keycodes 100/108/103); clean-room Hynitron CST3XX touch (I2C 0x5a, protocol via reg 0xD0xx, no firmware update).
- Board facts recovered: touch overlay in `odmdtbo` (`tpd-resolution` 800×1280, EINT 1, `vtouch` = VLDO28 2.8 V, I2C node `mediatek,cap_touch@5d`, driver forces 0x5a); panel ID check reads reg 0xA1 == 0x8802; RTC ioctls 36-byte numbers but 40-byte copies (stock quirk preserved); vendor modules: `wmt_drv`, `wlan_drv_gen2`, `bt_drv`, `fmradio_drv`, `gps_drv`, `wmt_chrdev_wifi`.
- Not ported (non-critical): accelerometers MSA311/mir3da, BT CVSD (SCO voice), ODM battery sysfs, AEE powerkey hooks, S5K3L2 camera.

### 2026-11-20 — device day 1: M1 recon + M2 backup (nothing written to the device)

**Device ≠ package.** The unit runs an older build: `T04_50_2_16_4inch_M404_ST7701S_sh1282G003_MECHEN_V1.0_20250305` (kernel 2025-03-05 `es01@blueshark03`, LK `k50v1_64_bsp-f7015dd0dd-20250305151445`, fingerprint spoofed as `Teclast/M40_Plus_ROW…:12/SP1A…`). Verified it doesn't matter for our kernel: device boot.img header + appended DTB are **identical** to the 2026 package, `odmdtbo` overlay decompiles **identical**, panel/battery tables + touch/keys/exFAT strings are **byte-identical** in the device kernel, and the device's own vendor modules (which differ byte-wise from the package's) **pass `check_modversions.py`** against our build.

M1 (`device/m1/`, git-ignored):
- 480×800 @ 240 dpi; eMMC is **16 GB** (`Q313MB`; userdata 11.4 GB), partition map otherwise = scatter.
- **SELinux is Permissive** on the shipping device (security finding: should be enforcing).
- `ro.boot.flash.locked=1`, `verifiedbootstate=green`, `veritymode=enforcing`; `sys.oem_unlock_allowed=1`; `ro.product.first_api_level=26`.
- fastboot: `unlocked: no`, `secure: yes`, `oem lks = 1`, `flashing get_unlock_ability = 16777216` (allowed). Baseband `MOLY.LR11.W1630.MD.MP.V217.2`.
- **BROM: `Target config 0x0`: SBC, SLA, DAA all disabled** → no hardware signature enforcement; device always recoverable via BROM.
- Developer options: tapping the wrong About line launches the Teksun factory test (don't run it). **BROM key combo = Volume Down** while plugging USB with the device off.

M2 (`device/m2/`, 3.9 GB, `SHA256SUMS`): all 32 GPT partitions except `userdata`, both eMMC boot areas (preloader, `EMMC_BOOT` header, boot1 == boot2), primary + backup GPT. `nvram` and `proinfo` are genuinely all-zero on this unit (two identical reads); calibration is in `nvdata`. system/vendor/cache verified clean ext4, build.prop + all vendor `.ko` match the live device.

Tooling notes: mtkclient in `.venv-mtk` (git-ignored) needs (a) `--preloader <package preloader_k50v1_64_bsp.bin>` placed **before** the subcommand (DRAM init; RAM only), (b) a local patch making its FUSE import optional (`mtk_da_handler.py`, catch `OSError`), (c) chunked reads for big partitions: single long reads die with USB pipe errors on macOS → `kernel/tools/firmware/mtk-chunked-read.sh` (32 MiB, resumable).

## Next session checklist (device day)

1. ~~M0 leftovers~~ done 2026-11-20. M0 leftovers: install mtkclient (`pip install git+https://github.com/bkerler/mtkclient`), set up the flash-log convention.
2. **M1** read-only recon (getprop: `ro.boot.verifiedbootstate`, `ro.boot.flash.locked`, `ro.product.first_api_level`, resolution; `fastboot getvar all`, `fastboot oem lks`, `fastboot flashing get_unlock_ability`); mtkclient target config (SBC/SLA/DAA).
3. **M2** full backup (mtkclient `rl` all partitions, incl. nvram/nvdata/proinfo); verify + copy offsite.
4. **M3** unlock (wipes data) → `fastboot boot` the **stock** boot.img repacked by our tool (`./build.sh selftest` output is identical anyway) → then `fastboot boot kernel/out/boot-<stamp>.img`.
5. First-boot checks for our kernel: `adb shell cat /proc/version` (3.18.119, our build stamp); display (which panel? `dmesg | grep -i lcm`); touch (`getevent -lp`, `dmesg | grep HYN`); side keys (`getevent` → codes 100/108/103); `lsmod`/`dmesg | grep -i wmt` (vendor modules loaded); Wi-Fi scan, BT pairing + A2DP playback; exFAT SD card; charging/battery %; suspend/resume (touch + keys after wake).
6. If all good: record in flash log, then start M9 step 1 (3.18.140 stable merge).

## Ongoing RE (any time, no device needed)

- [ ] Ghidra on `kernel_with_symbols_fixed.elf` (`ghidra_proj_v3`): audit MTK download-mode USB handling, verify no kernel-side kill-switch counterpart, read audio path if needed for launcher integration
- [ ] `sdupdate` update.zip signature policy: decompile recovery (`recovery_root/`) enough to know whether an SD-update must be signed — determines whether M4+ can also ship as update.zips
- [ ] Watch the k50v1 TWRP ecosystem for new device trees/kernel dumps (same ODM family)

---

## Open decisions

| # | Question | Default lean | Decide by |
|---|---|---|---|
| D1 | Keep or strip GMS (Play Store, GmsCore, Chrome)? | strip in v2 if music app unaffected | end of M4 testing |
| D2 | Final base: debloated stock vs LOS 18.1 GSI | stock for stability; GSI if it boots clean | end of M6 |
| D3 | Repartition to grow system (for GApps GSI or headroom)? | no unless blocked | only if M6 fails on size |
| D4 | Remove `sdupdate` in final builds (has MASTER_CLEAR)? | remove in "production" build, keep in "service" image | after M6 |
| D5 | Re-enable real dm-verity on final image? | only if we control recovery trust too | post-M6 |
| D6 | Kernel rebuild at all? | only if M7 finds verified source and M3 says SBC off | end of M7 |

## Rules of engagement

1. **No flashing without a completed M2 backup** — no exceptions, including "trivial" tests.
2. **Never flash `preloader`** (and avoid `lk`/`lk2` unless specifically working on them) — a bad preloader can require BROM-mode rescue.
3. **One logical change per flash**, logged below — keeps failure attribution cheap.
4. Rollback is always: download mode (or fastboot, if it still boots) → reflash M2 dump of the affected partition.
5. Keep `_analysis/` images read-only after verification; work on copies.

## Flash log

| Date | Partition(s) | Image / hash | Result | Notes |
|---|---|---|---|---|
| 2026-11-20 | — (unlock) | `fastboot flashing unlock` | OK, `unlocked: yes`, userdata wiped | first write-type action; first boot after wipe ~5 min |
| 2026-11-20 | boot | `kernel/out/boot-20261118-201249.img` sha256 786f5e84591bb58d… | **FAIL: boot loop** (LK orange screen → reset, no USB, no ADB); early-crash log lost (exited via recovery, which overwrote pstore) | first custom kernel; `fastboot boot` proved non-functional on this LK (RAM image ignored, reboots to flash). Rollback: `fastboot flash boot device/m2/partitions/boot.bin` |
| 2026-11-20 | boot | `device/m2/partitions/boot.bin` (backup, sha256 verified) | OK, stock kernel boots | rollback via fastboot (loop → Volume Up boot menu → recovery → "Reboot to bootloader") |
| 2026-11-20 | boot | `boot-20261118-201249.img` (attempt 2) → restored `boot.bin` | loop again; **log captured**: ~8.6 s then storm of `[SPM] IRQ1 HANDLER SHOULD NOT BE EXECUTED` → WDT | exit via Volume Up → Fastboot keeps pstore |
| 2026-11-20 | boot | `boot-20261120-142500-DIAG-spm.img` sha256 7cd693ca… | loop; log: no SPM storm, but M4U IRQ storm (sta=0) at 3.1 s → **root cause: INT_POL polarity writes dropped** (tree writes directly / SiP 0x287; stock uses ATF SiP 0x82000201) | DIAG: SPM aux IRQ rate-limited + disabled after 50 hits |
| 2026-11-20 | boot | `boot-20261120-143334-polfix-DIAG.img` sha256 d859b55a… | loop; **no IRQ storms** (polarity fix confirmed); clean panic at 2.94 s: NULL deref in `pinctrl_select_state` from `mtk_mt6331_codec_dev_probe` (tree's FIH ext-amp pinctrl24, absent on this board) | patch 0014 polarity fix + DIAG |



claude --resume fab0cf85-c2f0-4b7c-a06d-7579cda6123f 
