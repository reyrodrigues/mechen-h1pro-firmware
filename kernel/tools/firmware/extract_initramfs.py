#!/usr/bin/env python3
"""Find and extract the embedded initramfs (gzip cpio) inside an MTK kernel image."""
import sys, gzip, os, zlib

def find_gzip_streams(data):
    streams = []
    i = 0
    while True:
        i = data.find(b'\x1f\x8b\x08', i)
        if i < 0: break
        d = zlib.decompressobj(16 + zlib.MAX_WBITS)
        try:
            out = d.decompress(data[i:])
            if len(out) > 10000:  # only meaningful streams
                streams.append((i, out))
        except Exception:
            pass
        i += 1
    return streams

if __name__ == '__main__':
    src, outdir = sys.argv[1], sys.argv[2]
    os.makedirs(outdir, exist_ok=True)
    data = open(src, 'rb').read()
    print(f'kernel size: {len(data)}')
    streams = find_gzip_streams(data)
    for idx, (off, out) in enumerate(streams):
        p = f'{outdir}/initramfs_{idx}.cpio'
        open(p, 'wb').write(out)
        print(f'stream @{off:#x}: {len(out)} bytes -> {p} (starts {out[:8]!r})')
