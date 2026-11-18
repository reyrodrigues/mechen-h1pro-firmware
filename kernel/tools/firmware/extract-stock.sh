#!/bin/bash
# Extract everything the build needs from the stock MECHEN firmware package into kernel/stock/:
#   stock/boot.img        header template, stock DTB, VB1.0 signature reference
#   stock/kernel_image    uncompressed stock kernel (input for tools/gen_*.py, symbol work)
#   stock/kernel_config   stock IKCONFIG (reference; harness/stock.config is the committed copy)
#   stock/vendor_ko/*.ko  vendor kernel modules (modversions check on every build)
# Usage: tools/firmware/extract-stock.sh <firmware dir or .zip>
set -euo pipefail
HERE=$(cd "$(dirname "$0")" && pwd); ROOT=$(cd "$HERE/../.." && pwd)
SRC=$1; OUT=$ROOT/stock; mkdir -p "$OUT/vendor_ko"
DEBUGFS=$(command -v debugfs || echo /opt/homebrew/opt/e2fsprogs/sbin/debugfs)
[ -x "$DEBUGFS" ] || { echo "need e2fsprogs (brew install e2fsprogs)"; exit 1; }
TMP=$(mktemp -d); trap 'rm -rf "$TMP"' EXIT

if [ -f "$SRC" ]; then unzip -q "$SRC" -d "$TMP/zip"; SRC=$(dirname "$(find "$TMP/zip" -name boot.img | head -1)"); fi
for f in boot.img vendor.img; do [ -f "$SRC/$f" ] || { echo "missing $SRC/$f"; exit 1; }; done

cp "$SRC/boot.img" "$OUT/boot.img"
python3 -I - "$OUT/boot.img" "$OUT/kernel_image" "$ROOT/harness" <<'PY'
import sys, zlib
sys.path.insert(0, sys.argv[3]); import mkbootimg
_, _, blob = mkbootimg.parse(open(sys.argv[1], 'rb').read())
d = zlib.decompressobj(31); img = d.decompress(blob)
open(sys.argv[2], 'wb').write(img)
print(f'kernel_image: {len(img)} bytes, appended dtb {len(d.unused_data)} bytes')
PY
python3 -I - "$OUT/kernel_image" "$OUT/kernel_config" <<'PY'
import sys, gzip
d = open(sys.argv[1], 'rb').read(); i = d.find(b'IKCFG_ST')
open(sys.argv[2], 'wb').write(gzip.decompress(d[i + 8:d.find(b'IKCFG_ED')]))
print('kernel_config: extracted')
PY
python3 -I "$HERE/simg2img.py" "$SRC/vendor.img" "$TMP/vendor_raw.img"
for m in $("$DEBUGFS" -R 'ls /lib/modules' "$TMP/vendor_raw.img" 2>/dev/null | tr -s ' ' '\n' | grep '\.ko$'); do
    "$DEBUGFS" -R "dump /lib/modules/$m $OUT/vendor_ko/$m" "$TMP/vendor_raw.img" 2>/dev/null
done
ls "$OUT/vendor_ko"
cmp -s "$OUT/kernel_config" "$ROOT/harness/stock.config" && echo "stock config matches harness/stock.config" || echo "WARNING: stock config differs from harness/stock.config"
