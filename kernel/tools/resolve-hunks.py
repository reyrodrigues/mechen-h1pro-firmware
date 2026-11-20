#!/usr/bin/env python3
"""Resolve git conflict regions in a file by picking one side per hunk.

Usage: resolve-hunks.py <file> <choice>[,<choice>...]
  choice per conflict region, in order: 'theirs' (the cherry-picked upstream side) or 'ours' (HEAD).
  A single choice applies to all regions. Everything outside conflict markers is untouched.
"""
import re, sys

path, spec = sys.argv[1], sys.argv[2].split(',')
s = open(path).read()
pat = re.compile(r'<<<<<<< [^\n]*\n(.*?)=======\n(.*?)>>>>>>> [^\n]*\n', re.S)
regions = pat.findall(s)
choices = spec * len(regions) if len(spec) == 1 else spec
assert len(choices) == len(regions), f'{len(regions)} regions, {len(choices)} choices'
it = iter(choices)
out = pat.sub(lambda m: m.group(2) if next(it) == 'theirs' else m.group(1), s)
assert '<<<<<<<' not in out and '>>>>>>>' not in out
open(path, 'w').write(out)
print(f'{path}: resolved {len(regions)} region(s): {",".join(choices)}')
