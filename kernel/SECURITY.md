# Security backport tracker

Plan and process: `../FIRMWARE_REVERSE_ENGINEERING.md` → M9. Baseline: Linux 3.18.119 (MTK alps P), Android security patch level 2021-02-05 (framework; the kernel's effective level is older).

Rule: every series must keep `out/modversions.txt` all OK (vendor Wi-Fi/BT/FM/GPS modules) and pass a `fastboot boot` test before it is kept.

## Series status

| Series | Source | Patches | Status |
|---|---|---|---|
| 1 | linux-3.18.y stable v3.18.120 … v3.18.140 | `patches-stable/1000-…` | **done 2026-11-20** (p23-stable): 1,393 clean, 8 hand-resolved, 26 already present, 9 not built, 4 skipped; see `patches-stable/STABLE-LOG.txt`, `TRIAGE.txt` |
| 2 | AOSP `kernel/common` `deprecated/android-3.18` (to 2021-01, fixes not in 3.18.140) | `patches-stable/1001-…` | **done 2026-11-20** (p24-aosp): 49 Android-tagged commits since 2018-08 → 5 applied, 2 hand-applied, 9 already present, 1 reverted, 3 skipped, 29 not built; see `AOSP-LOG.txt`, `AOSP-TRIAGE.txt` |
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

## Series 1 notes (2026-11-20)

- Tooling: `tools/stable-merge.sh <first> <last>` (cherry-pick per release, skips "Linux 3.18.N" version bumps so vermagic stays `3.18.119`), `tools/pick.sh <sha>`, `tools/resolve-hunks.py`, `tools/abi/typedump.sh` (genksyms type diff between branches).
- ABI adaptations (vendor modules use modversions): `struct net.hash_mix` moved to the end + `#ifndef __GENKSYMS__`; `inet_peer.n_redirects` and `kmem_cache.cpu_partial` type change hidden from genksyms; `netns_nf_frag` memory-saving commit 338ec134e reverted (layout change, no security value).
- Hand-resolved security fixes: ION kref overflow (MTK had the helper but ignored its result), ION_IOC_{MAP,SHARE} UAF (+ MTK `ion_drv_get_handle` adapted, ERR_PTR check fixed), tty wipe buffer, xfrm template families, swiotlb address leak, ext4 bg_flags, USB gadget set_interface race, PM direct_complete.
- Already present in the MTK tree (26), e.g. vmacache_flush_all removal, /proc/iomem privileged addresses, unix in-flight fds, ashmem/ion/sync-fence fixes, ext4 xattr magic/corruption checks, arm64 pfn_valid.
