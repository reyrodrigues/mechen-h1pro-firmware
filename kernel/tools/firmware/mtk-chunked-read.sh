#!/bin/bash
# Resumable chunked partition read via mtkclient (long single reads time out on macOS USB).
# Usage: mtk-chunked-read.sh <outdir> <preloader.bin> <name:offset_hex:length_hex>...
# Each partition is read in 32 MiB chunks to <outdir>/<name>.chunks/NNNN.bin; chunks already present
# with the right size are skipped, so re-running after a disconnect resumes. When every chunk of a
# partition is present it is concatenated to <outdir>/<name>.bin.
set -euo pipefail
HERE=$(cd "$(dirname "$0")" && pwd)
MTK=${MTK:-$HERE/../../../.venv-mtk/bin/mtk}
OUT=$1; PRELOADER=$2; shift 2
CHUNK=$((32 * 1024 * 1024))
cmds=()
for spec in "$@"; do
    IFS=: read -r name off len <<< "$spec"
    off=$((off)); len=$((len)); mkdir -p "$OUT/$name.chunks"
    n=$(( (len + CHUNK - 1) / CHUNK ))
    for ((i = 0; i < n; i++)); do
        f=$(printf '%s/%s.chunks/%04d.bin' "$OUT" "$name" "$i")
        sz=$(( i == n - 1 ? len - i * CHUNK : CHUNK ))
        [ -f "$f" ] && [ "$(stat -f %z "$f")" = "$sz" ] && continue
        rm -f "$f"
        cmds+=("ro $(printf '0x%x' $((off + i * CHUNK))) $(printf '0x%x' "$sz") $f")
    done
done
if [ ${#cmds[@]} -gt 0 ]; then
    echo "== ${#cmds[@]} chunks to read"
    multi=$(IFS=';'; echo "${cmds[*]}")
    "$MTK" --preloader "$PRELOADER" multi "$multi" || true
fi
status=0
for spec in "$@"; do
    IFS=: read -r name off len <<< "$spec"; len=$((len))
    n=$(( (len + CHUNK - 1) / CHUNK )); have=0
    for ((i = 0; i < n; i++)); do
        f=$(printf '%s/%s.chunks/%04d.bin' "$OUT" "$name" "$i")
        sz=$(( i == n - 1 ? len - i * CHUNK : CHUNK ))
        [ -f "$f" ] && [ "$(stat -f %z "$f")" = "$sz" ] && have=$((have + 1))
    done
    if [ "$have" = "$n" ]; then
        cat "$OUT/$name.chunks"/*.bin > "$OUT/$name.bin" && echo "$name: complete ($len bytes)"
    else
        echo "$name: $have/$n chunks, re-run to resume"; status=1
    fi
done
exit $status
