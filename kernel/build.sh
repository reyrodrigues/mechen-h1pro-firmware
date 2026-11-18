#!/bin/bash
# Host entry point: build the kernel in Docker and produce a boot image in kernel/out/.
#   ./build.sh                 full build (DTB_MODE=stock)
#   ./build.sh selftest        prove the repacker reproduces stock boot.img byte-for-byte
#   ./build.sh shell           interactive shell in the build container
#   ./build.sh reprepare       re-create source branch mp3-build from the pinned commit + harness/patches
#   DTB_MODE=built JOBS=8 KEEP_GOING=1 ./build.sh
# One-time setup: ./setup.sh <stock firmware dir or zip>   (see BUILDING.md)
set -euo pipefail
cd "$(dirname "$0")"
ROOT=$(pwd)
STOCK_DIR=${STOCK_DIR:-$ROOT/stock}
IMAGE=mp3kernel-build:3.18
PROFILE=mp3kernel

[ -f "$STOCK_DIR/boot.img" ] || { echo "no $STOCK_DIR/boot.img: run ./setup.sh <firmware> first"; exit 1; }

if [ "${1:-}" = selftest ]; then
    exec python3 -I harness/mkbootimg.py --selftest "$STOCK_DIR/boot.img"
fi

# Case-sensitive source volume (the kernel tree breaks on case-insensitive APFS).
[ -d src/linux ] || hdiutil attach kernel-src.sparseimage -mountpoint src -nobrowse >/dev/null

if [ "${1:-}" = reprepare ]; then
    git -C src/linux checkout -q --detach
    git -C src/linux branch -D -q mp3-build 2>/dev/null || true
fi
# Local fixes on top of the pinned upstream commit (branch mp3-build).
git -C src/linux rev-parse -q --verify mp3-build >/dev/null || harness/prepare-source.sh src/linux harness/patches
[ "${1:-}" = reprepare ] && exit 0

# Docker runtime: dedicated colima profile (vz + Rosetta for the x86_64 GCC 4.9 toolchain).
if ! colima status -p "$PROFILE" >/dev/null 2>&1; then
    echo "== starting colima profile $PROFILE"
    colima start -p "$PROFILE" --vm-type vz --vz-rosetta --cpu 6 --memory 8 --disk 40
fi
export DOCKER_CONTEXT=colima-$PROFILE

mkdir -p src/obj out
docker build -q --platform linux/amd64 -t "$IMAGE" harness >/dev/null

RUN=(docker run --rm --platform linux/amd64
     -v "$ROOT/src/linux:/src" -v "$ROOT/src/obj:/obj" -v "$ROOT/out:/out"
     -v "$ROOT/harness:/harness:ro" -v "$STOCK_DIR:/stock:ro"
     -e DTB_MODE="${DTB_MODE:-stock}" -e KEEP_GOING="${KEEP_GOING:-}" -e JOBS="${JOBS:-}")
if [ "${1:-}" = shell ]; then
    exec "${RUN[@]}" -it "$IMAGE" bash
fi
"${RUN[@]}" "$IMAGE" bash /harness/build-in-container.sh
