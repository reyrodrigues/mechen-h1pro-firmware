#!/bin/bash
# Cherry-pick one upstream commit onto the current branch of src/linux and show its conflict regions.
cd "$(dirname "$0")/../src/linux"
sha=$1
git log -1 --format="== %h %s" "$sha"
if git -c user.name=mp3-harness -c user.email=harness@localhost cherry-pick -x "$sha" >/dev/null 2>&1; then
    echo "applied cleanly"; exit 0
fi
files=$(git diff --name-only --diff-filter=U)
[ -z "$files" ] && { echo "EMPTY (already in tree)"; git cherry-pick --abort; exit 2; }
for f in $files; do echo "--- $f"; python3 -I - "$f" <<'P'
import re,sys
s=open(sys.argv[1]).read()
for i,(a,b) in enumerate(re.findall(r'<<<<<<< [^\n]*\n(.*?)=======\n(.*?)>>>>>>> [^\n]*\n',s,re.S)):
    print(f'[region {i}] OURS:\n{a}[region {i}] THEIRS:\n{b}')
P
done
exit 1
