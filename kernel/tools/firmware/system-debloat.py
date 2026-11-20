#!/usr/bin/env python3
"""Remove ODM/risky apps from a raw ext4 `system` image (M4), without mounting it.

Usage: system-debloat.py <input system.img (raw ext4)> <output image>

Works on a copy (APFS clone when possible). Deletes each listed app directory recursively with
debugfs, then runs `e2fsck -fn` to verify the result. The input is never modified.
"""
import os, re, shutil, subprocess, sys

DEBUGFS = shutil.which('debugfs') or '/opt/homebrew/opt/e2fsprogs/sbin/debugfs'
E2FSCK = shutil.which('e2fsck') or '/opt/homebrew/opt/e2fsprogs/sbin/e2fsck'

# Directory -> reason. Paths are inside the system-as-root image.
REMOVE = {
    '/system/priv-app/SystemLock': 'remote kill-switch over plain HTTP (47.120.15.138:7900)',
    '/system/priv-app/ValidationTools': 'Teksun factory test (com.teksun.factorytest)',
    '/system/priv-app/EngineerMode': 'MTK EngineerMode (MASTER_CLEAR and other broad perms)',
    '/system/app/AutoDialer': 'com.example stub with CALL_PHONE',
    '/system/priv-app/sdupdate': 'com.example.call: applies /sdcard/update.zip, MASTER_CLEAR/RECOVERY',
    '/system/app/ATMWifiMeta': 'MTK factory Wi-Fi META stub',
    '/system/priv-app/Baidu_Location': 'Baidu network location',
    '/system/app/LPPeService': 'MTK LPPe location helper',
    '/system/app/NlpService': 'MTK network location provider',
    '/system/app/MtkNlp': 'MTK network location provider',
}


def dbg(img, cmd):
    return subprocess.run([DEBUGFS, '-R', cmd, img], capture_output=True, text=True).stdout


def walk(img, path):
    """Return (files, dirs) under path; dirs listed deepest-first."""
    files, dirs = [], []
    for line in dbg(img, f'ls -p {path}').splitlines():
        m = re.match(r'/(\d+)/(\d+)/\d+/\d+/(.*?)/', line)
        if not m or m.group(3) in ('.', '..'):
            continue
        child = f'{path}/{m.group(3)}'
        if m.group(2).startswith('04'):
            f, d = walk(img, child)
            files += f
            dirs += d
        else:
            files.append(child)
    dirs.append(path)
    return files, dirs


def main():
    src, out = sys.argv[1], sys.argv[2]
    if os.path.exists(out):
        os.remove(out)
    if subprocess.run(['cp', '-c', src, out]).returncode != 0:   # APFS clone, else plain copy
        shutil.copyfile(src, out)
    cmds = []
    for path, why in REMOVE.items():
        if not dbg(out, f'stat {path}').strip() or 'not found' in dbg(out, f'stat {path}'):
            print(f'  skip (absent) {path}')
            continue
        files, dirs = walk(out, path)
        cmds += [f'rm {f}' for f in files] + [f'rmdir {d}' for d in dirs]
        print(f'  remove {path}: {len(files)} files, {len(dirs)} dirs  ({why})')
    cmdfile = out + '.debugfs'
    with open(cmdfile, 'w') as f:
        f.write('\n'.join(cmds) + '\n')
    r = subprocess.run([DEBUGFS, '-w', '-f', cmdfile, out], capture_output=True, text=True)
    errs = [l for l in r.stderr.splitlines() if l.strip() and not l.startswith('debugfs ')]
    if errs:
        print('debugfs errors:\n  ' + '\n  '.join(errs[:20]))
        sys.exit(1)
    os.remove(cmdfile)
    left = [p for p in REMOVE if 'not found' not in dbg(out, f'stat {p}') and dbg(out, f'stat {p}').strip()]
    fsck = subprocess.run([E2FSCK, '-fn', out], capture_output=True, text=True)
    print(f'still present: {left or "none"}')
    print('e2fsck -fn:', 'clean' if fsck.returncode == 0 else f'rc={fsck.returncode}\n{fsck.stdout[-1500:]}')
    sys.exit(0 if (not left and fsck.returncode == 0) else 1)


if __name__ == '__main__':
    main()
