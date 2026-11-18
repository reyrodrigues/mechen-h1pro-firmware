#!/bin/bash
# One-time setup for the MECHEN H1-Pro kernel build on macOS (Apple Silicon).
#   ./setup.sh <stock firmware dir or .zip>
# Creates the case-sensitive source volume, clones the pinned kernel tree, fetches the AOSP verity
# test key, extracts the stock artifacts and prepares the patched source branch.
set -euo pipefail
cd "$(dirname "$0")"
ROOT=$(pwd)
FW=${1:?usage: ./setup.sh <stock firmware dir or zip>}
SRC_REPO=https://github.com/zhiluan233/android_kernel_cyberfurryrobot_cfb001
SRC_COMMIT=a30c78c0f612b29a30f4aeb6e89a39b80b0ea3c3
AOSP_TAG=android-9.0.0_r61

need() { command -v "$1" >/dev/null || { echo "missing: $1 ($2)"; exit 1; }; }
need git "xcode-select --install"; need python3 "brew install python"; need openssl "brew install openssl"
need docker "brew install docker"; need colima "brew install colima"; need hdiutil "macOS"
command -v debugfs >/dev/null || [ -x /opt/homebrew/opt/e2fsprogs/sbin/debugfs ] || { echo "missing: brew install e2fsprogs"; exit 1; }

echo "== 1/5 stock artifacts"
tools/firmware/extract-stock.sh "$FW"

echo "== 2/5 case-sensitive source volume"
[ -f kernel-src.sparseimage ] || hdiutil create -size 12g -type SPARSE -fs "Case-sensitive APFS" -volname mp3kernel kernel-src.sparseimage >/dev/null
mkdir -p src
[ -d src/linux ] || mount | grep -q "$ROOT/src" || hdiutil attach kernel-src.sparseimage -mountpoint src -nobrowse >/dev/null

echo "== 3/5 kernel source @ $SRC_COMMIT"
if [ ! -d src/linux/.git ]; then
    git init -q src/linux
    git -C src/linux fetch -q --depth 1 "$SRC_REPO" "$SRC_COMMIT"
    git -C src/linux checkout -q --detach FETCH_HEAD
fi
[ "$(git -C src/linux rev-parse "$SRC_COMMIT^{commit}" 2>/dev/null)" = "$SRC_COMMIT" ] || { echo "pinned commit not present"; exit 1; }

echo "== 4/5 AOSP verity test key (public; stock boot.img is signed with it)"
mkdir -p harness/keys
for f in verity.pk8 verity.x509.pem; do
    [ -s harness/keys/$f ] || curl -sf "https://android.googlesource.com/platform/build/+/refs/tags/$AOSP_TAG/target/product/security/$f?format=TEXT" | base64 -d > harness/keys/$f
done
openssl x509 -in harness/keys/verity.x509.pem -noout -serial | grep -q 970F983909AA8949 || { echo "unexpected verity cert"; exit 1; }

echo "== 5/5 patched source branch + repacker selftest"
git -C src/linux rev-parse -q --verify mp3-build >/dev/null || harness/prepare-source.sh src/linux harness/patches
./build.sh selftest
echo "== setup done. Next: ./build.sh"
