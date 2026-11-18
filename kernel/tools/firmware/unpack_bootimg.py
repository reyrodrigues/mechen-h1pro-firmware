#!/usr/bin/env python3
"""Unpack an Android boot/recovery image into kernel + ramdisk + dtb."""
import struct, sys, os, gzip, io
try:
    import lz4.frame
except ImportError:
    lz4 = None

def read_header(path):
    with open(path, 'rb') as f:
        data = f.read()
    assert data[:8] == b'ANDROID!', f'not an Android boot image: {path}'
    (magic, kernel_size, kernel_addr, ramdisk_size, ramdisk_addr,
     second_size, second_addr, tags_addr, page_size, dt_size,
     unused, name, cmdline, img_id) = struct.unpack('<8s10I16s512s32s', data[:608])
    hdr = {
        'kernel_size': kernel_size, 'kernel_addr': hex(kernel_addr),
        'ramdisk_size': ramdisk_size, 'ramdisk_addr': hex(ramdisk_addr),
        'second_size': second_size, 'page_size': page_size,
        'dt_size': dt_size, 'name': name.rstrip(b'\0').decode(errors='replace'),
        'cmdline': cmdline.rstrip(b'\0').decode(errors='replace'),
    }
    # boot_img_hdr v0 (MTK usually v0 with dt appended)
    pos = page_size
    kernel = data[pos:pos+kernel_size]
    pos += ((kernel_size + page_size - 1)//page_size)*page_size
    ramdisk = data[pos:pos+ramdisk_size]
    pos += ((ramdisk_size + page_size - 1)//page_size)*page_size
    second = data[pos:pos+second_size]
    pos += ((second_size + page_size - 1)//page_size)*page_size
    dtb = data[pos:pos+dt_size]
    # AVB footer check (last 64 bytes)
    avb = None
    tail = data[-64:]
    if tail[:4] == b'AVBf':
        avb = struct.unpack('<4sII4xQIIQ', tail[:44])
    # MTK header v1 (magic 0x88168858) sometimes prepended to kernel/ramdisk
    return hdr, kernel, ramdisk, second, dtb, avb, data

def align(v, a): return (v + a - 1)//a*a

def try_decompress(ramdisk):
    if ramdisk[:2] == b'\x1f\x8b':
        return gzip.decompress(ramdisk), 'gzip'
    if lz4 is not None and (ramdisk[:4] == b'\x04\x22\x4d\x18' or ramdisk[:4]==b'\x02\x21\x4c\x18'):
        try:
            d = lz4.frame.decompress(ramdisk)
            return d, 'lz4'
        except Exception:
            pass
    if ramdisk[:6] == b'\xfd7zXZ\x00':
        import lzma
        return lzma.decompress(ramdisk), 'xz'
    return ramdisk, 'raw'

if __name__ == '__main__':
    src, outdir = sys.argv[1], sys.argv[2]
    os.makedirs(outdir, exist_ok=True)
    hdr, kernel, ramdisk, second, dtb, avb, _ = read_header(src)
    print(f'== {src}')
    for k, v in hdr.items(): print(f'  {k:14} {v}')
    print(f'  avb_footer    {avb}')
    # strip possible MTK magic headers on kernel/ramdisk blobs
    def strip_mtk(b):
        if len(b) > 512 and struct.unpack('<I', b[:4])[0] == 0x88168858:
            off = struct.unpack('<I', b[8:12])[0]
            return b[512:512+struct.unpack("<I", b[4:8])[0]] , True
        return b, False
    kernel, km = strip_mtk(kernel)
    ramdisk, rm = strip_mtk(ramdisk)
    print(f'  mtk_kernel_hdr {km}, mtk_ramdisk_hdr {rm}')
    open(f'{outdir}/kernel.gz' if kernel[:2]==b'\x1f\x8b' else f'{outdir}/kernel','wb').write(kernel)
    open(f'{outdir}/ramdisk.comp','wb').write(ramdisk)
    dec, method = try_decompress(ramdisk)
    print(f'  ramdisk       {ramdisk_size_ if False else hdr["ramdisk_size"]} bytes, {method} -> {len(dec)} bytes')
    open(f'{outdir}/ramdisk.cpio','wb').write(dec)
    if dtb: open(f'{outdir}/dtb','wb').write(dtb)
    print('  -> extracted to', outdir)
