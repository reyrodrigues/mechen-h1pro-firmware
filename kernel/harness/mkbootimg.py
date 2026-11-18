#!/usr/bin/env python3
"""Repack a MECHEN H1-Pro (MT6750) boot image.

Layout of the stock boot.img (verified 2026-11-18):
  Android boot header v1, page 2048, no ramdisk, no second stage.
  kernel blob = gzip(Image) + appended DTB ("Image.gz-dtb").
  All header fields (addresses, cmdline, os_version) are copied from the
  stock image so only the kernel blob changes.

Usage:
  mkbootimg.py --stock boot.img --kernel Image.gz-dtb -o boot-new.img
  mkbootimg.py --stock boot.img --image Image --dtb appended.dtb -o boot-new.img
  mkbootimg.py --selftest boot.img       # repack stock blob, must be byte-identical
"""
import argparse, gzip, hashlib, os, struct, subprocess, sys, tempfile

HERE = os.path.dirname(os.path.abspath(__file__))
KEY = os.path.join(HERE, 'keys', 'verity.pk8')
CERT = os.path.join(HERE, 'keys', 'verity.x509.pem')

HDR_FMT = '<8s10I16s512s32s1024s'          # v0 part (1632 bytes)
V1_FMT = '<IQI'                             # recovery_dtbo_size, _offset, header_size


def parse(data):
    assert data[:8] == b'ANDROID!', 'not an Android boot image'
    f = list(struct.unpack(HDR_FMT, data[:1632]))
    hv = f[9]
    v1 = struct.unpack(V1_FMT, data[1632:1648]) if hv >= 1 else None
    page = f[8]
    kernel = data[page:page + f[1]]
    return f, v1, kernel


def pad(b, page):
    return b + b'\0' * ((-len(b)) % page)


def der(tag, body):
    n = len(body)
    if n < 0x80:
        ln = bytes([n])
    else:
        b = n.to_bytes((n.bit_length() + 7) // 8, 'big')
        ln = bytes([0x80 | len(b)]) + b
    return bytes([tag]) + ln + body


def der_int(v):
    b = v.to_bytes(max(1, (v.bit_length() + 8) // 8), 'big')
    return der(0x02, b)


def boot_signature(image, target='/boot'):
    """AOSP VB1.0 boot_signer (BootSignature.java) with the AOSP verity test key."""
    cert = subprocess.run(['openssl', 'x509', '-in', CERT, '-outform', 'DER'],
                          check=True, stdout=subprocess.PIPE).stdout
    attrs = der(0x30, der(0x13, target.encode()) + der_int(len(image)))
    with tempfile.NamedTemporaryFile() as t:
        t.write(image + attrs); t.flush()
        sig = subprocess.run(['openssl', 'dgst', '-sha256', '-sign', KEY, '-keyform', 'DER', t.name],
                             check=True, stdout=subprocess.PIPE).stdout
    alg = der(0x30, der(0x06, bytes.fromhex('2a864886f70d01010b')))  # sha256WithRSA, no NULL params (matches AOSP)
    return der(0x30, der_int(1) + cert + alg + attrs + der(0x04, sig))


def build(stock, kernel_blob, sign=True):
    f, v1, _ = parse(stock)
    page, hv = f[8], f[9]
    assert f[3] == 0 and f[5] == 0, 'stock image has ramdisk/second; extend this tool first'
    if v1:
        assert v1[0] == 0, 'stock image has recovery_dtbo; extend this tool first'
    f[1] = len(kernel_blob)
    sha = hashlib.sha1()
    for blob in (kernel_blob, b'', b''):          # kernel, ramdisk, second
        sha.update(blob)
        sha.update(struct.pack('<I', len(blob)))
    if hv >= 1:
        sha.update(b'')
        sha.update(struct.pack('<I', 0))         # recovery_dtbo
    f[13] = sha.digest().ljust(32, b'\0')
    hdr = struct.pack(HDR_FMT, *f)
    if v1:
        hdr += struct.pack(V1_FMT, *v1)
    img = pad(hdr, page) + pad(kernel_blob, page)
    return img + boot_signature(img) if sign else img


def main():
    ap = argparse.ArgumentParser()
    ap.add_argument('--stock')
    ap.add_argument('--kernel', help='Image.gz-dtb (gzip kernel + appended dtb)')
    ap.add_argument('--image', help='uncompressed Image (with --dtb)')
    ap.add_argument('--dtb')
    ap.add_argument('-o', '--out')
    ap.add_argument('--no-sign', action='store_true', help='omit the VB1.0 boot signature trailer')
    ap.add_argument('--selftest', metavar='STOCK_BOOT_IMG')
    a = ap.parse_args()

    if a.selftest:
        stock = open(a.selftest, 'rb').read()
        _, _, kblob = parse(stock)
        new = build(stock, kblob)
        ok = new == stock
        print(f'selftest: repack of stock kernel blob is {"BYTE-IDENTICAL" if ok else "DIFFERENT"} '
              f'({len(new)} vs {len(stock)} bytes)')
        if not ok:
            n = min(len(new), len(stock))
            diff = next((i for i in range(n) if new[i] != stock[i]), n)
            print(f'  first difference at offset {diff:#x}')
        sys.exit(0 if ok else 1)

    if not (a.stock and a.out):
        ap.error('--stock and -o are required')
    stock = open(a.stock, 'rb').read()
    if a.kernel:
        blob = open(a.kernel, 'rb').read()
    elif a.image and a.dtb:
        blob = gzip.compress(open(a.image, 'rb').read(), 9, mtime=0) + open(a.dtb, 'rb').read()
    else:
        ap.error('give --kernel, or --image and --dtb')
    out = build(stock, blob, sign=not a.no_sign)
    open(a.out, 'wb').write(out)
    print(f'wrote {a.out}: {len(out)} bytes, kernel blob {len(blob)} bytes, sha1 {hashlib.sha1(out).hexdigest()}')


if __name__ == '__main__':
    main()
