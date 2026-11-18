#!/usr/bin/env python3
"""Extract the DTB appended to the gzip kernel in a stock boot.img."""
import sys, zlib
sys.path.insert(0, __import__('os').path.dirname(__file__))
import mkbootimg

_, _, blob = mkbootimg.parse(open(sys.argv[1], 'rb').read())
d = zlib.decompressobj(31)
d.decompress(blob)
dtb = d.unused_data
assert dtb[:4] == b'\xd0\x0d\xfe\xed', 'no DTB after gzip kernel'
open(sys.argv[2], 'wb').write(dtb)
print(f'stock dtb: {len(dtb)} bytes')
