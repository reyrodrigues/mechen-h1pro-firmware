#!/bin/bash
# Runs inside the Docker image. Mounts: /src (kernel tree), /out (artifacts), /harness, /stock.
set -euo pipefail

OBJ=/obj
STAMP=$(date -u +%Y%m%d-%H%M%S)
DTB_MODE=${DTB_MODE:-stock}          # stock = append the stock DTB (safest); built = use the tree's Image.gz-dtb
JOBS=${JOBS:-$(nproc)}
mkdir -p "$OBJ"

echo "== toolchain: $(${CROSS_COMPILE}gcc --version | head -1)"
echo "== source:    $(git -C /src log -1 --format='%h %s' 2>/dev/null || echo 'not a git tree')"

# 1. Config: start from the exact stock config (IKCONFIG), plus optional local overrides.
cp /harness/stock.config "$OBJ/.config"
[ -f /harness/config.fragment ] && cat /harness/config.fragment >> "$OBJ/.config"
make -C /src O="$OBJ" olddefconfig >/dev/null

# 2. Report stock options the tree could not honour (driver missing from the source).
grep -E '^CONFIG_[A-Za-z0-9_]+=' /harness/stock.config | sort > /tmp/want
grep -E '^CONFIG_[A-Za-z0-9_]+=' "$OBJ/.config" | sort > /tmp/got
comm -23 /tmp/want /tmp/got > /out/config-lost.txt || true
echo "== stock config lines not reproduced: $(wc -l < /out/config-lost.txt)  (see out/config-lost.txt)"

# Board-critical drivers: without these the device has no screen/touch/keys.
CRITICAL='CUSTOM_KERNEL_LCM|TOUCHSCREEN_MTK_CTSXXXX|EXFAT'
MISSING_CRITICAL=$(grep -E "$CRITICAL" /out/config-lost.txt || true)
LCM_OK=1
for p in st7701boe nv3049f; do
    [ -d "/src/drivers/misc/mediatek/lcm/$p" ] || { echo "!! LCM driver missing in tree: $p"; LCM_OK=0; }
done

# 3. Build.
# dtbs only when the tree's DTB is used: it runs MTK's 32-bit x86 DrvGen, which Rosetta can't execute.
TARGETS="Image.gz"; [ "$DTB_MODE" = built ] && TARGETS="Image.gz-dtb"
rm -f "$OBJ/arch/arm64/boot/Image.gz"
set +e
make -C /src O="$OBJ" -j"$JOBS" ${KEEP_GOING:+-k} LOCALVERSION= KCFLAGS="-Wno-error=frame-larger-than=" $TARGETS > /out/build.log 2>&1
RC=$?
set -e
grep -E ' error|Error [0-9]' /out/build.log | head -20 || true
[ $RC = 0 ] && [ -f "$OBJ/arch/arm64/boot/Image.gz" ] || { echo "!! build failed (rc=$RC), see out/build.log"; exit 1; }

# 4. Package.
case "$DTB_MODE" in
  stock) python3 /harness/extract_stock_dtb.py /stock/boot.img /tmp/stock.dtb
         cat "$OBJ/arch/arm64/boot/Image.gz" /tmp/stock.dtb > /tmp/Image.gz-dtb ;;
  built) cp "$OBJ/arch/arm64/boot/Image.gz-dtb" /tmp/Image.gz-dtb ;;
  *) echo "bad DTB_MODE"; exit 1 ;;
esac

# Vendor kernel modules (Wi-Fi/BT/FM/GPS): CRCs + vermagic must match or they won't load.
MODS_OK=1
if ls /stock/vendor_ko/*.ko >/dev/null 2>&1; then
    python3 /harness/check_modversions.py "$OBJ/vmlinux" /stock/vendor_ko/*.ko | tee /out/modversions.txt || MODS_OK=0
fi

if [ -n "$MISSING_CRITICAL" ] || [ "$LCM_OK" = 0 ]; then
    NAME="boot-$STAMP-UNSAFE-missing-board-drivers.img"
    echo "!! Board drivers missing — image is for build validation ONLY, do not flash:"
    echo "$MISSING_CRITICAL" | sed 's/^/   /'
elif [ "$MODS_OK" = 0 ]; then
    NAME="boot-$STAMP-WARN-vendor-modules-mismatch.img"
    echo "!! Vendor modules will not load (no Wi-Fi/BT/FM/GPS) — see out/modversions.txt"
else
    NAME="boot-$STAMP.img"
fi
python3 /harness/mkbootimg.py --stock /stock/boot.img --kernel /tmp/Image.gz-dtb -o "/out/$NAME"
cp "$OBJ/.config" "/out/${NAME%.img}.config"
(cd /out && sha256sum "$NAME" > "$NAME.sha256")
{ strings "$OBJ/arch/arm64/boot/Image" | grep 'Linux version' | head -1 || true; } | tee "/out/${NAME%.img}.version"
echo "== done: out/$NAME"
