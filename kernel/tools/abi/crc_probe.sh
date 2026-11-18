#!/bin/bash
# Usage (in build container): crc_probe.sh <path/file.c relative to /src> <symbol> [sed-expr applied to preprocessed source]
# Prints the genksyms CRC of <symbol> for the (optionally edited) preprocessed source.
set -e
f=$1; sym=$2; expr=${3:-}
make -s -C /src O=/obj LOCALVERSION= KCFLAGS=-D__GENKSYMS__ "${f%.c}.i" >/dev/null 2>&1
i=/obj/${f%.c}.i
if [ -n "$expr" ]; then sed -e "$expr" "$i" > /tmp/probe.i; else cp "$i" /tmp/probe.i; fi
/obj/scripts/genksyms/genksyms < /tmp/probe.i | grep -E "__crc_${sym}\b" || echo "no crc for $sym"
