#!/usr/bin/env bash
# 15-second scripted demo: 1 user (Emacs) + 3 agents collaborating on
# the same task.md via stile. Run live in your terminal to preview;
# render to GIF/MP4 with `vhs demo.tape`.
set -euo pipefail

DIR="$(cd "$(dirname "$0")" && pwd)"
WORK="${1:-/tmp/stile-twitter-demo}"

# Idempotent setup: clean working dir + seeded task.md + sidecar.
"$DIR/setup.sh" "$WORK" >/dev/null
cd "$WORK"

pause() { sleep "${1:-1.0}"; }

clear

echo '$ cat task.md'
cat task.md
pause 2.0

echo
echo '# 3 agents capture the SAME base, edit disjoint sections, save'
pause 1.0

# orchestrate.py prints one line per agent: "agent:role  save: <mode>"
# Expect: direct, merged, merged -- the "concurrent edits, no losses" story.
python3 "$DIR/orchestrate.py" task.md
pause 1.5

echo
echo '$ cat task.md'
cat task.md
pause 4.0

echo
echo '# four writers, no lost edits, file always consistent.'
pause 1.5
