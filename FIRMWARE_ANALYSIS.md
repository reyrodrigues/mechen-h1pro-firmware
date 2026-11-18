# MECHEN H1-Pro (T04) Firmware Analysis & Custom Firmware Plan

Analysis date: 2026-11-18 · Firmware package: `T04_50_2_16_4inch_M404_ST7701S_sh1282G003_MECHEN_20260331`

## 1. Device identity

| Item | Value |
|---|---|
| Product | MECHEN H1-Pro (folder/model code T04, 4-inch, ST7701S LCD driver, sh1282G003 touch) |
| SoC | MediaTek MT6750 (scatter file; kernel/platform code `mt6755`, k50v1_64_bsp EVB), arm64 |
| Storage | eMMC, ~8 GB (scatter ends at ~7.4 GB; userdata 3 GB, system ~1.9 GB, vendor ~1.5 GB) |
| Android | 9 (SDK 28), security patch **2021-02-05** |
| Kernel | Linux 3.18.119, built 2026-03-31 (GCC 4.9), 17.5 MB Image, config embedded (IKCONFIG) |
| Display | 240 dpi (ST7701S panel; exact resolution to confirm on device, likely 480×800) |
| ODM chain | Built by "ms06@blueshark04"; factory-test apps from Teksun (`com.teksun.factorytest`) |

## 2. Boot chain & verified-boot posture

Chain: eMMC boot1/2 `preloader` → `lk` (+ `lk2` backup) → `boot` (kernel + appended DTB, **empty ramdisk**) → system-as-root (`system.img` contains `/init`).

- **No AVB anywhere** (no `avb` vbmeta, no AVB footers on boot images).
- MTK dm-verity: `verity_key` present in system root and recovery ramdisk, but the normal-boot fstab (`vendor/etc/fstab.mt6755`) mounts system/vendor with `verify=...,recoveryonly` → **dm-verity is NOT enforced in normal boot**. System partition can be modified freely at runtime/by flashing.
- The package ships both plain and `-verified` images; the verified variants carry ~3.7 KB appended MTK SBC signatures. LK contains `[SBC] img vfy disabled` strings — this only proves the code path exists, not that verification is off on this unit. Whether signature verification is active depends on the device's seccfg (SBL/SBC lock state) — **must be tested on the actual device**; these ODM devices almost always ship with SBC off.
- LK exposes **full fastboot** (`flashing unlock`, `flashing get_unlock_ability`, `oem lks`, `oem ultraflash`, `oem reboot-recovery`) with on-screen unlock confirmation, plus MTK download mode (SP Flash Tool) and meta/factory modes.
- Kernel cmdline/DTB: `console=ttyMT3,921600n1` — **UART console available** for debugging if pads are exposed.

## 3. Security findings (ranked)

1. **Remote kill-switch over plain HTTP** — `priv-app/SystemLock` (`com.android.systemlock`, 5.8 MB) POSTs `p0=device_lock&p1=<model>` to `http://47.120.15.138:7900/IOtaBlueshark/otaserver` and locks the device when the server replies "lock". Unencrypted, unauthenticated, MITM-trivial. Also listens for a `System_Lock` broadcast. → **Remove.**
2. **EOL software stack** — Android 9 with 2021-02 patch level on Linux 3.18.119. Hundreds of unpatched public CVEs (kernel + framework). No realistic path to a current Android on this BSP; mitigation = shrink attack surface (below) + disable network services.
3. **Spoofed build fingerprint** — `ro.build.fingerprint=BLU/G90/G0310WW:10/QP1A.190711.020/1585383273:user/release-keys` (a BLU G90 phone, Android 10). Play-cert spoofing; Play Integrity will fail regardless. Set honest values in custom build.
4. **Privileged factory/ODM apps** — `EngineerMode` (4.7 MB, broad perms incl. MASTER_CLEAR), `ValidationTools` (`com.teksun.factorytest`), `AutoDialer` (`com.example.*`, CALL_PHONE, code-less stub), `ATMWifiMeta` (code-less MTK stub), `sdupdate` (`com.example.call`, MASTER_CLEAR/REBOOT/RECOVERY — applies `/sdcard/update.zip` via recovery). → Remove EngineerMode/ValidationTools/AutoDialer/ATMWifiMeta; treat sdupdate as the flashing tool, then remove or neuter.
5. **Baidu location stack** — `Baidu_Location`, `LPPeService`, `NlpService`, `MtkNlp` in priv-app/app. Privacy-relevant; remove if GPS/location unused (MP3 player!).
6. **Full GMS preinstalled** — Phonesky (Play Store), GmsCore, GoogleServicesFramework, Chrome. Privacy + unkillable update channel; optional removal in custom build.
7. Kernel config hardening present but dated: SELinux (enforcing, `CHECKREQPROT_VALUE=1`), seccomp, stack protector strong, hardened usercopy, DEBUG_RODATA; `CONFIG_MODULES=y` (unsigned module loading possible on 3.18 — but requires root).
8. `ro.oem_unlock_supported=1`, ADB is secure (RSA auth, `ro.adb.secure=1`, debuggable=0) — props are production-grade. (Stray `ro.debuggable=1` strings also exist in both images, likely debug-ramdisk/script fragments — confirm with `getprop` on device.)

**Not found:** no `su` binaries, no adware/lockscreen-ad SDKs, no embedded URLs in other components (the OTA endpoint exists only in SystemLock).

## 4. Custom firmware plan

Guiding decision: no AVB + verity unenforced + fastboot/download-mode access ⇒ we can modify `system.img`/`vendor.img` **in place** and reflash. No kernel rebuild needed for the launcher goal.

### Phase 0 — On-device recon (30 min, no risk)
- `adb shell getprop` (confirm resolution, density, fingerprint, lock state), `cat /proc/partitions`, `ls /system/priv-app`.
- Try `adb reboot bootloader` → check fastboot (`fastboot devices`, `fastboot oem lks` → lock state). If no fastboot menu, boot to download mode (usually Volume-… combo) and verify SP Flash Tool sees the device.
- Confirm whether the device SBC-verifies images: if `fastboot flash` of a trivially modified boot image (e.g. changed cmdline byte) boots fine, verification is off. (Do this only after Phase 1 backup.)

### Phase 1 — Full backup (mandatory before any modification)
- `SP Flash Tool` → Readback (or `mtkclient` on a Linux box/VM — open-source, works without the vendor DA) of **every partition** per `MT6750_Android_scatter.txt`; especially preloader, lk, lk2, boot, recovery, proinfo, nvram, nvdata, seccfg, and the raw system/vendor.
- Also dump via `dd` from a rooted/ADB shell where possible as a cross-check (boot/recovery/lk are readable block devices per fstab).
- Store backups + original zip in two places. Note NVRAM/nvdata contain Wi-Fi/BT calibration — losing them = degraded radio.

### Phase 2 — Modding toolchain (reusable pipeline)
Working copy already exists: `_analysis/system_raw.img` + `vendor_raw.img` (raw ext4, from my `simg2img.py`).
- Primary workflow (any OS): `debugfs`/`e2fsprogs` to add/remove files in the ext4 image (this is how the current analysis extracted APKs). Works for APK drops and build.prop edits.
- For heavier edits: Linux VM or Docker (`docker run -it --rm -v $PWD:/w ubuntu` + `apt install e2fsprogs android-sdk-libsparse-utils simg2img`): loop-mount the ext4 image, edit, `img2simg` back to sparse.
- Flash with SP Flash Tool (Download Only, per-partition: system, boot) or `fastboot flash system system.img`.
- Alternative no-unlock path: craft a signed-agnostic `/sdcard/update.zip` and use `sdupdate` → recovery. Need to check recovery's OTA signature policy (test-keys vs enforced cert) — try first with a trivial package before relying on it.
- Flashing custom boot/lk later: repack with the same layout (gzip kernel + appended DTB, MTK header on lk). Tools: `mkbootimg` (MTK fork), or byte-level repack keeping original headers.

### Phase 3 — Bespoke launcher (the main product goal)
- Stock launcher: `MtkLauncher3` (`com.android.launcher3`, priv-app). Music app: `MusicBspPlus` (`com.android.music`).
- Build a normal Android app (Kotlin/Compose or classic Views; minSdk 28, targetSdk 28 to avoid scoped-storage surprises on this old build), HOME + DEFAULT categories, optimized for a 4″ 240dpi single-hand screen (huge touch targets, dark theme for OLED-style battery, no swipe-gesture assumptions).
- Music-first UX: query MediaStore, control via `MediaBrowserService`Compat to the stock music app or embed ExoPlayer/Media3 directly. Hardware keys (vol/next/prev) via `KeyEvent` handling in launcher + `AudioManager`.
- Install as `/system/priv-app/CustomLauncher/CustomLauncher.apk` (debugfs write into system_raw.img), remove or disable `MtkLauncher3` (delete its dir, and remove its HOME intent-filter by simply deleting the APK — fallback HOME in `Settings` if needed during dev: `adb shell cmd package set-home-activity`).
- No platform signature needed for HOME. If privileged perms are wanted later (WRITE_SECURE_SETTINGS etc.), add a sysconfig whitelist at `/system/etc/sysconfig/customlauncher-whitelist.xml`.
- Dev loop: `adb install -r` the launcher on the stock device first (it can run as a normal app), iterate UX, then bake into the image when stable.

### Phase 4 — Security hardening of the image
- Delete from `/system/priv-app` + `/system/app`: `SystemLock`, `EngineerMode`, `ValidationTools`, `AutoDialer`, `ATMWifiMeta`, `Baidu_Location`, `LPPeService`(+`NlpService`/`MtkNlp` if location unused), optionally `Phonesky`/`GmsCore`/`GoogleServicesFramework`/`Chrome` (test consequences for MusicBspPlus first — it's MTK, likely GMS-free).
- `build.prop`: honest `ro.build.fingerprint`/model, `persist.sys.usb.config=mtp` (keep, or `none` + toggle), leave `ro.adb.secure=1`, `ro.debuggable=0` for daily use; make an explicit "dev image" variant when iterating.
- After finalizing: decide on `sdupdate` — remove for production devices (it can master-clear), keep a "service" build with it for future updates.
- Consider enabling dm-verity for real (regenerate hashtree with `verity_utils`, drop `recoveryonly` from fstab) once the image is final — protects the system partition at runtime. Only worth it if we also control recovery/LK trust; otherwise skip.
- Optional deeper hardening (Phase 5+): rebuild kernel 3.18 from MTK k50v1 sources with patch backports (kspp-style), disable CONFIG_MODULES, real IMA/keys — significant effort, do only if the device will handle sensitive data.
- Network posture: if the player is used offline/USB-transfer only, disable Wi-Fi/BT at init level (or just never configure) — shrinks the MITM/remote surface to near zero.

### Phase 5 — Test & rollback protocol
- Keep boot/lk/preloader **unmodified** until the end ⇒ any bad system flash is recoverable via download mode + original images.
- Test matrix after each flash: boot, launcher default, music playback incl. headset buttons, USB-MTP from macOS, SD card, BT headphones, battery/charge UI.
- Rollback = reflash original system/vendor/boot from the Phase-1 backup (SP Flash Tool, Download Only).

## 5. "Better OS" assessment — GSI / LineageOS feasibility (2026-11-18)

- **Bottom line: a newer/better OS *is* installable** — not as an official port, but as a GSI (newer Android framework on the stock vendor + kernel). The hard ceiling is the 3.18 kernel, not the bootloader or partitions.
- **Official LineageOS: not available** (device unsupported; a full port needs ODM kernel sources + device tree work — impractical).
- **GSI route: viable.** Verified in firmware: proper VINTF device manifest (`/vendor/etc/vintf/manifest.xml`, target-level 2) with the standard HIDL HAL set (audio 4.0, graphics, sensors, keymaster, gatekeeper, usb, wifi, bt, health), `first_api_level` (vendor contains both `=26` and `=28` — confirm on device; Treble support holds either way given the manifest), no AVB / verity unenforced, unlockable via fastboot or download mode.
- **Target image class:** Android 11 LineageOS 18.1 GSI, **arm64 A-only vanilla** (no GApps). Android 11 is the safe ceiling on kernel 3.18. Android 12+ needs eBPF features (netd/traffic accounting) that 3.18 lacks; some phh-based A12/A13 GSIs have been reported to boot on 3.18 devices with workarounds — treat as experimental, try only after A11 works. (Unverified offline.) Alternatives: phh AOSP GSI (fallback if LOS GSI hits MTK quirks), /e/OS or iodé GSI builds.
- **Size check:** system partition 0x72800000 ≈ 1.79 GiB; vanilla LOS GSIs ≈ 1.0–1.3 GiB → fits. GApps GSIs do not fit without repartitioning (cache 432 MB / userdata 3 GB are donors).
- **Expected keep-working:** audio, display (ST7701S), touch, USB-MTP, SD, hardware keys (all vendor/kernel-side). **Likely quirks:** Wi-Fi/BT firmware loading may need phh-Treble setting tweaks; camera HAL uncertain (likely no camera); userdata must be reformatted on switch (FDE→GSI mismatch).
- **Security reality check:** GSI swaps the framework to ~2023 patch level and removes all ODM components, but the kernel remains 3.18.119 — its CVEs are only fixable by a kernel rebuild.
- **Flash outline (after Phase 1 backup):** `fastboot flashing unlock` → `fastboot flash system <los18-aonly-vanilla>.img` → wipe cache/data → boot → configure phh Treble app. Rollback: download mode + reflash stock system/vendor/boot.

## 6. Kernel rebuild feasibility (2026-11-18)

**Verdict: yes, conditionally** — rebuild the same Linux 3.18 MTK kernel (patches/hardening/features), not a version upgrade. 3.18→4.x would mean porting MTK's whole driver stack (months); KASLR/PAN don't exist on 3.18 arm64 regardless.

Already in hand: exact `.config` (IKCONFIG → `kernel/harness/stock.config`), base DTB (`_analysis/boot_out/appended.dtb`, decompile with `dtc`), toolchain target (GCC 4.9 aarch64), and the boot image packaging (gzip kernel + appended DTB, page 2048 — repacker = reverse of `unpack_bootimg.py`).

Source routes, best-first:
1. Same-board ecosystem: alps Android 9 MT6750 kernel dumps on GitHub; a TWRP device tree for this exact k50v1_64_bsp board exists (fingerprint from the same blueshark build farm). Est. days.
2. MT6755 3.18 GPL trees (e.g., kernel-3.18_t8p, AOSP kernel/mediatek android-3.18) + port board files for ST7701S LCM / sh1282 touch. Est. 1–3 weeks.
3. GPL request to MECHEN/ODM (legally required, historically ignored).

What it buys: CVE cherry-picks beyond 2021-02 (android-3.18 common is long EOL — exact end date unverified; backports are manual), config hardening (CONFIG_MODULES=n, DEVMEM off, KALLSYMS off, SELinux CHECKREQPROT=0), feature backports (e.g., WireGuard). Prerequisite: verify SBC is off (boot a trivially modified boot.img) before investing.

Exotic alternative: mainline/postmarketOS — ST7701S panel driver exists in mainline; loses Android, new userspace; separate project.

## 7. Kernel decompilation / RE status (2026-11-18)

The extracted 17.5 MB ARM64 Image (CONFIG_KALLSYMS=y) has been symbolized via `vmlinux-to-elf` (installed in `_analysis/.venv`): **`kernel_with_symbols_fixed.elf`** — 46,135 symbols, base `0xffffffc000080000` (an earlier version used the wrong base `…82000` and was deleted), loads directly in Ghidra/IDA; `kernel_symbols.txt` holds the flat list. Enables per-function disassembly/pseudo-C (no source recovery — rebuilding still needs real source per §6), kernel-side audits (310 sys_* functions, 1,176 MTK symbols; no backdoor-style names found), and — most usefully — verifying a candidate source dump by building it with our `.config` and diffing symbol addresses against this binary.

## 8. Artifacts created during this analysis (`_analysis/`)

- `unpack_bootimg.py`, `extract_initramfs.py`, `simg2img.py` — reusable tools
- `boot_out/` (kernel Image, kernel config, appended DTB), `recovery_out/` + `recovery_root/` (recovery ramdisk tree incl. `prop.default`, `verity_key`, `etc/recovery.fstab`)
- `system_raw.img` / `vendor_raw.img` (raw ext4, 1.9/1.5 GB — the modding base), `sys_extract/` (build.prop etc.), `apk_extract/` (8 APKs + SystemLock/sdupdate decompiled), `lk_strings.txt`, `kernel_config.txt`
