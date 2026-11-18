# MP3Firmware: MECHEN H1-Pro custom firmware

Custom firmware work for the MECHEN H1-Pro (model T04) 4" Android MP3 player: MediaTek MT6750, Android 9, Linux 3.18.119.

| Document | Contents |
|---|---|
| [`FIRMWARE_ANALYSIS.md`](FIRMWARE_ANALYSIS.md) | Device identity, boot chain, security findings, feasibility (GSI, kernel, postmarketOS) |
| [`FIRMWARE_REVERSE_ENGINEERING.md`](FIRMWARE_REVERSE_ENGINEERING.md) | Working plan (milestones M0–M9), session log, open decisions, rules of engagement, flash log |
| [`kernel/BUILDING.md`](kernel/BUILDING.md) | **Build the kernel from scratch** |
| [`kernel/README.md`](kernel/README.md) | Kernel harness layout and current build status |

Quick start (macOS, Apple Silicon):

```sh
brew install python openssl e2fsprogs docker colima
cd kernel
./setup.sh /path/to/T04_50_2_16_4inch_M404_ST7701S_sh1282G003_MECHEN_20260331.zip
./build.sh
```

**Status (2026-11-18):** kernel builds into a signed stock-layout `boot.img`; all vendor modules pass the ABI check. **Nothing has been tested on hardware yet.** Read the rules of engagement in `FIRMWARE_REVERSE_ENGINEERING.md` before flashing anything.

Not in this repository (by design): the stock firmware package and anything extracted from it (`kernel/stock/`, `_analysis/`), the kernel source checkout (fetched at a pinned commit), build outputs, Ghidra installs/projects, and the AOSP test key (fetched by `setup.sh`). Patches 0005/0006 contain panel-init and battery tables recovered from the stock kernel.
