#!/bin/bash
# Creates branch mp3-build on top of the pinned upstream commit:
#   1. applies harness/patches/*.patch
#   2. removes build artifacts the uploader committed (break out-of-tree builds: "source is not clean")
set -euo pipefail
SRC=$(cd "$1" && pwd); PATCHES=$(cd "$2" && pwd)
BASE=a30c78c0f612b29a30f4aeb6e89a39b80b0ea3c3
G=(git -C "$SRC" -c user.name=mp3-harness -c user.email=harness@localhost)

"${G[@]}" checkout -q -B mp3-build "$BASE"
"${G[@]}" am -q "$PATCHES"/*.patch
"${G[@]}" rm -r -q --cached --ignore-unmatch \
    include/config include/generated arch/arm64/include/generated .version kernel/time/timeconst.h \
    scripts/basic/fixdep scripts/dtc/dtc scripts/kconfig/conf scripts/mod/modpost >/dev/null
"${G[@]}" commit -q -m "Remove committed build artifacts (generated headers, host binaries)"
"${G[@]}" clean -fdxq -e '!*' -- include/config include/generated arch/arm64/include/generated \
    .version kernel/time/timeconst.h scripts/basic/fixdep scripts/dtc/dtc scripts/kconfig/conf scripts/mod/modpost
# 3. Security backports (M9): combined linux-3.18.y stable series + ABI adaptations, unless STABLE=0.
#    Per-commit provenance and conflict resolutions: harness/patches-stable/STABLE-LOG.txt, TRIAGE.txt.
STABLE_DIR="$PATCHES/../patches-stable"
if [ "${STABLE:-1}" != 0 ] && ls "$STABLE_DIR"/*.patch >/dev/null 2>&1; then
    for p in "$STABLE_DIR"/*.patch; do
        "${G[@]}" apply --index --binary "$p"
        "${G[@]}" commit -q -m "$(basename "$p" .patch)" -m "See harness/patches-stable/STABLE-LOG.txt"
    done
fi
echo "== source prepared: $("${G[@]}" log --oneline "$BASE"..mp3-build | wc -l | tr -d ' ') local commits on $BASE"
