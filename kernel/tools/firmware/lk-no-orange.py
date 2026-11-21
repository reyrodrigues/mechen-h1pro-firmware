#!/usr/bin/env python3
"""Remove the 5-second "Orange State" warning from the stock MECHEN H1-Pro LK (lk.bin).

Usage: lk-no-orange.py <stock LK> <output>

Accepted inputs: `lk.img` or `lk-verified.img` from the stock package
T04_50_2_16_4inch_M404_ST7701S_sh1282G003_MECHEN_20260331, or a 1 MiB dump of the lk partition from a
player running the later LK build (same routine, at a different offset).

LK is Thumb-2 code loaded at 0x46000000 behind a 512-byte MTK header. The boot-state check at
0x4603235c tail-calls 0x46032238 for the orange (unlocked) state. That routine clears the screen,
prints "Orange State" / "Your device has been unlocked and can't be trusted" / "Your device will
boot in 5 seconds", sleeps 5000 ms and returns 0 (continue booting). We replace its first
instruction with `movs r0,#0; bx lr`. The yellow/red error paths are untouched, and so is
androidboot.verifiedbootstate=orange on the kernel command line.

Only the exact stock image is accepted (sha256 checked), and every patched byte is checked first.
"""
import hashlib, struct, sys

HDR, BASE = 0x200, 0x46000000
# sha256 of the stock image -> load address of the orange-warning routine
KNOWN = {
    'a70a5a2f04d7348f1170bf74329e643a7f6c17a8a6c4195776a15e8115a69952': 0x46032238,  # lk partition dump (later build)
    '46e7982510b7bff05cdb329a76cc595d030822777d120d2d2525171e1eb5f2d1': 0x46031fe8,  # package lk.img
    'b76f226c9ed336a5f81744a663fff9320acd62fafefc7b90c513ad6640165339': 0x46031fe8,  # package lk-verified.img
}
EXPECT = bytes.fromhex('08b5f3f777ff')      # push {r3,lr}; bl 0x4602612c
PATCH = bytes.fromhex('00207047')          # movs r0,#0; bx lr


def main():
    src, out = sys.argv[1], sys.argv[2]
    b = bytearray(open(src, 'rb').read())
    FUNC = KNOWN.get(hashlib.sha256(b).hexdigest())
    if FUNC is None:
        sys.exit('not a stock LK this patch was made for')
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
