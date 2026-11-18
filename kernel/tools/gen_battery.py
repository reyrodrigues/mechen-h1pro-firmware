#!/usr/bin/env python3
"""Replace the battery tables in mt6755 mt_battery_meter_table.h with the stock MECHEN H1-Pro tables.

Stock kernel (base 0xffffffc000080000) uses the SINGLE-profile code path (fgauge_get_profile
compares temperatures and returns fixed tables; fgauge_get_saddles() == 100), so the tree's
MTK_MULTI_BAT_PROFILE_SUPPORT must be off. Scalar parameters (Q_MAX, R_FG, temperatures...)
come from the stock DTB `mediatek,bat_meter` node, which the harness appends unchanged.

Usage: gen_battery.py <stock kernel Image> <kernel tree>
"""
import re, struct, sys

BASE = 0xffffffc000080000
TABLES = {  # name -> (VA, entries); addresses from the decompiled stock fgauge_get_profile*/BattThermistorConverTemp
    'Batt_Temperature_Table': (0xffffffc001097dc8, 17),
    'battery_profile_t0': (0xffffffc001097e50, 100),
    'battery_profile_t1': (0xffffffc001098170, 100),
    'battery_profile_t2': (0xffffffc001097aa0, 100),
    'battery_profile_t3': (0xffffffc001098490, 100),
    'r_profile_t0': (0xffffffc0010987b0, 100),
    'r_profile_t1': (0xffffffc001098ad0, 100),
    'r_profile_t2': (0xffffffc001098df0, 100),
    'r_profile_t3': (0xffffffc001099110, 100),
}
ZEROED = {'battery_profile_temperature': 100, 'r_profile_temperature': 100}  # runtime-filled (stock: BSS, 0x320 bytes)

HDR = 'drivers/misc/mediatek/include/mt-plat/mt6755/include/mach/mt_battery_meter_table.h'
METER_H = 'drivers/misc/mediatek/include/mt-plat/mt6755/include/mach/mt_battery_meter.h'


def body(rows):
    return '\n'.join(f'\t{{{a}, {b}}},' for a, b in rows)


def replace_array(src, name, rows, only_first=False):
    pat = re.compile(r'(\b' + name + r'\[\]\s*=\s*\{)(.*?)(\n\};)', re.S)
    n = 0

    def sub(m):
        nonlocal n
        n += 1
        if only_first and n > 1:
            return m.group(0)
        return m.group(1) + '\n' + body(rows) + m.group(3)
    out = pat.sub(sub, src)
    assert n >= 1, f'{name} not found'
    return out


def main():
    img = open(sys.argv[1], 'rb').read()
    tree = sys.argv[2]
    p = f'{tree}/{HDR}'
    s = open(p).read()
    for name, (va, n) in TABLES.items():
        rows = [struct.unpack_from('<ii', img, va - BASE + 8 * i) for i in range(n)]
        # Batt_Temperature_Table exists twice (NTC 10k / 47k variants): stock uses NTC 10k = first one.
        s = replace_array(s, name, rows, only_first=(name == 'Batt_Temperature_Table'))
    for name, n in ZEROED.items():
        s = replace_array(s, name, [(0, 0)] * n)
    open(p, 'w').write(s)

    m = f'{tree}/{METER_H}'
    t = open(m).read()
    t = t.replace('#define MTK_MULTI_BAT_PROFILE_SUPPORT',
                  '/* #define MTK_MULTI_BAT_PROFILE_SUPPORT */ /* stock MECHEN kernel: single profile */')
    open(m, 'w').write(t)
    print('battery tables + single-profile written')


if __name__ == '__main__':
    main()
