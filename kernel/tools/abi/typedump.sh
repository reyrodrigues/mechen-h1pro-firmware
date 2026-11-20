#!/bin/bash
# In build container: genksyms -T type dump for given source files on the currently checked-out branch.
# Usage: typedump.sh <outdir> <file.c>...
out=$1; shift; mkdir -p "$out"
make -s -C /src O=/obj LOCALVERSION= olddefconfig >/dev/null 2>&1
for f in "$@"; do
  make -s -C /src O=/obj LOCALVERSION= KCFLAGS=-D__GENKSYMS__ "${f%.c}.i" >/dev/null 2>&1 || { echo "pp fail $f"; continue; }
  /obj/scripts/genksyms/genksyms -T "$out/$(echo ${f%.c} | tr / _).types" < "/obj/${f%.c}.i" > /dev/null 2>&1
done
