#!/usr/bin/env python3
"""Check that stock vendor kernel modules (.ko) will load on a newly built kernel.

The stock vendor partition loads wmt_drv, wlan_drv_gen2, bt_drv, gps_drv, fmradio_drv,
wmt_chrdev_wifi with CONFIG_MODVERSIONS: every imported symbol's CRC must equal the kernel's
__crc_<sym>, and vermagic must match exactly ("3.18.119 SMP preempt mod_unload modversions aarch64").

Usage: check_modversions.py <vmlinux ELF> <ko>...
Kernel CRCs are read from vmlinux __ksymtab{,_gpl} + __kcrctab{,_gpl}: exactly what the module loader checks.
"""
import re, struct, sys


def sections(elf):
    shoff = struct.unpack_from('<Q', elf, 0x28)[0]
    shentsize, shnum, shstrndx = struct.unpack_from('<HHH', elf, 0x3a)
    hdrs = [struct.unpack_from('<IIQQQQIIQQ', elf, shoff + i * shentsize) for i in range(shnum)]
    stroff = hdrs[shstrndx][4]
    out = {}
    for h in hdrs:
        name = elf[stroff + h[0]: elf.index(b'\0', stroff + h[0])].decode()
        out[name] = elf[h[4]: h[4] + h[5]] if h[1] != 8 else b''   # SHT_NOBITS has no file data
        out['@' + name] = h[3]                                     # sh_addr
    return out


def kernel_crcs(vmlinux):
    sec = sections(vmlinux)
    strs, saddr = sec['__ksymtab_strings'], sec['@__ksymtab_strings']
    crcs = {}
    for suffix in ('', '_gpl'):
        tab, crc = sec.get('__ksymtab' + suffix, b''), sec.get('__kcrctab' + suffix, b'')
        for i in range(len(tab) // 16):
            ptr = struct.unpack_from('<Q', tab, i * 16 + 8)[0] - saddr
            name = strs[ptr: strs.index(b'\0', ptr)].decode()
            crcs[name] = struct.unpack_from('<Q', crc, i * 8)[0] & 0xffffffff
    return crcs


def main():
    vml = open(sys.argv[1], 'rb').read()
    kcrc = kernel_crcs(vml)
    m = re.search(rb'Linux version (\S+)', vml)
    krel = m.group(1).decode() if m else '?'
    print(f'kernel release: {krel}   kernel CRCs: {len(kcrc)}')
    # symbols exported by the modules themselves (module-to-module deps, e.g. wmt_drv -> bt_drv)
    modexp = set()
    for ko in sys.argv[2:]:
        sec = sections(open(ko, 'rb').read())
        modexp |= {x.decode() for x in sec.get('__ksymtab_strings', b'').split(b'\0') if x}
    bad_total = 0
    for ko in sys.argv[2:]:
        elf = open(ko, 'rb').read()
        sec = sections(elf)
        vm = re.search(rb'vermagic=([^\0]*)', sec.get('.modinfo', b''))
        vermagic = vm.group(1).decode() if vm else '?'
        v = sec.get('__versions', b'')
        mism, missing = [], []
        for i in range(0, len(v), 64):
            crc = struct.unpack_from('<Q', v, i)[0] & 0xffffffff
            name = v[i + 8: v.index(b'\0', i + 8)].decode()
            if name not in kcrc:
                if name not in modexp:
                    missing.append(name)
            elif kcrc[name] != crc:
                mism.append(name)
        n = len(v) // 64
        vm_ok = vermagic.split()[0] == krel
        status = 'OK' if (not mism and not missing and vm_ok) else 'WILL NOT LOAD'
        bad_total += status != 'OK'
        print(f'{ko.split("/")[-1]:22} {status:14} imports={n} crc_mismatch={len(mism)} missing={len(missing)} '
              f'vermagic={"ok" if vm_ok else vermagic}')
        for s in (mism[:8] + missing[:4]):
            print(f'    {s}')
    sys.exit(1 if bad_total else 0)


if __name__ == '__main__':
    main()
