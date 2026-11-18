#!/usr/bin/env python3
"""Minimal Android sparse image -> raw image converter."""
import struct, sys

def main(src, dst):
    f = open(src, 'rb')
    hdr = f.read(28)
    magic, major, minor, file_hdr_sz, chunk_hdr_sz, blk_sz, total_blks, total_chunks, _ = struct.unpack('<IHHHHIIII', hdr)
    assert magic == 0xED26FF3A, f'not a sparse image: {magic:#x}'
    print(f'sparse v{major}.{minor} blk={blk_sz} total_blks={total_blks} chunks={total_chunks}')
    out = open(dst, 'wb')
    done = 0
    for i in range(total_chunks):
        ch = f.read(chunk_hdr_sz)
        ctype, reserved, num_blks, total_bytes = struct.unpack('<HHII', ch[:12])
        if ctype == 0xCAC1:  # raw
            sz = num_blks * blk_sz
            while sz:
                buf = f.read(min(1 << 22, sz))
                out.write(buf); sz -= len(buf)
        elif ctype == 0xCAC2:  # fill
            fill = f.read(4)
            out.write(fill * (num_blks * blk_sz // 4))
        elif ctype == 0xCAC3:  # dont care
            out.seek(num_blks * blk_sz, 1)
        elif ctype == 0xCAC4:  # crc
            f.read(4)
        done += num_blks
    out.truncate(total_blks * blk_sz)
    print(f'wrote {total_blks * blk_sz} bytes -> {dst}')

if __name__ == '__main__':
    main(sys.argv[1], sys.argv[2])
