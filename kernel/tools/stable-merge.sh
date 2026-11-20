#!/bin/bash
# Cherry-pick upstream linux-3.18.y stable releases onto the current branch of kernel/src/linux.
#   tools/stable-merge.sh <first N> <last N>      e.g. 120 140
# For each release v3.18.N it cherry-picks every commit in v3.18.(N-1)..v3.18.N (oldest first).
#   - The "Linux 3.18.N" version-bump commit is SKIPPED: the kernel must keep reporting 3.18.119,
#     otherwise vendor modules (vermagic "3.18.119 ...") stop loading.
#   - A commit that does not apply cleanly (conflict, or touches files absent from this tree) is
#     aborted and recorded in out/stable-merge/conflicts-N.txt for manual resolution.
#   - Applied commits get a trailer "Upstream-stable: v3.18.N <sha>".
# Requires: remote/tags v3.18.119..v3.18.140 fetched into src/linux (see kernel/SECURITY.md).
set -uo pipefail
cd "$(dirname "$0")/../src/linux"
OUT=../../out/stable-merge; mkdir -p "$OUT"
G=(git -c user.name=mp3-harness -c user.email=harness@localhost -c core.abbrev=12)
for ((n = $1; n <= $2; n++)); do
    prev=v3.18.$((n - 1)); cur=v3.18.$n
    : > "$OUT/conflicts-$n.txt"; ok=0; bad=0; skip=0
    for c in $("${G[@]}" rev-list --reverse --no-merges "$prev..$cur"); do
        subj=$("${G[@]}" log -1 --format=%s "$c")
        if [ "$subj" = "Linux 3.18.$n" ]; then skip=$((skip + 1)); continue; fi
        if "${G[@]}" cherry-pick -x "$c" >/dev/null 2>&1; then
            "${G[@]}" commit -q --amend -m "$("${G[@]}" log -1 --format=%B)
Upstream-stable: $cur $c" >/dev/null 2>&1
            ok=$((ok + 1))
        else
            files=$("${G[@]}" diff --name-only --diff-filter=U | tr '\n' ' ')
            "${G[@]}" cherry-pick --abort >/dev/null 2>&1 || "${G[@]}" reset -q --hard HEAD
            echo "$c $subj | $files" >> "$OUT/conflicts-$n.txt"
            bad=$((bad + 1))
        fi
    done
    echo "$cur: applied $ok, conflicts $bad, version-bump skipped $skip" | tee -a "$OUT/summary.txt"
done
