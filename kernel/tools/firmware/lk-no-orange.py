#!/usr/bin/env python3
"""Remove the 5-second "Orange State" warning from the stock MECHEN H1-Pro LK (lk.bin).

Usage: lk-no-orange.py <stock lk.bin> <output lk.bin>

LK is Thumb-2 code loaded at 0x46000000 behind a 512-byte MTK header. The boot-state check at
0x4603235c tail-calls 0x46032238 for the orange (unlocked) state. That routine clears the screen,
prints "Orange State" / "Your device has been unlocked and can't be trusted" / "Your device will
boot in 5 seconds", sleeps 5000 ms and returns 0 (continue booting). We replace its first
instruction with `movs r0,#0; bx lr`. The yellow/red error paths are untouched, and so is
androidboot.verifiedbootstate=orange on the kernel command line.

Only the exact stock image is accepted (sha256 checked), and every patched byte is checked first.
"""
import hashlib, struct, sys

STOCK_SHA256 = 'a70a5a2f04d7348f1170bf74329e643a7f6c17a8a6c4195776a15e8115a69952'
HDR, BASE = 0x200, 0x46000000
FUNC = 0x46032238
EXPECT = bytes.fromhex('08b5f3f777ff')      # push {r3,lr}; bl 0x4602612c
PATCH = bytes.fromhex('00207047')          # movs r0,#0; bx lr


def main():
    src, out = sys.argv[1], sys.argv[2]
    b = bytearray(open(src, 'rb').read())
    if hashlib.sha256(b).hexdigest() != STOCK_SHA256:
        sys.exit('not the stock lk.bin this patch was made for')
    magic, size = struct.unpack_from('<II', b, 0)
    assert magic == 0x58881688 and b[8:10] == b'lk', 'unexpected LK header'
    off = HDR + FUNC - BASE
    assert off + len(PATCH) <= HDR + size
    assert b[off:off + len(EXPECT)] == EXPECT, 'code at the patch site differs'
    # sanity: the 5000 ms delay (movw r0,#0x1388) is inside this routine
    assert bytes.fromhex('41f28830') in b[off:off + 0x40], 'delay not found in routine'
    b[off:off + len(PATCH)] = PATCH
    open(out, 'wb').write(b)
    print(f'patched {len(PATCH)} bytes at file offset {off:#x} (addr {FUNC:#x}); '
          f'sha256 {hashlib.sha256(b).hexdigest()}')


if __name__ == '__main__':
    main()
