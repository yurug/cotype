#!/usr/bin/env bash
# Seed the working dir for the multi-round Claude demo. Unlike setup.sh,
# this does NOT preallocate `## agent:role` slots -- the agents respond
# to the user's question by appending their own sections, just like a
# real shared-file collaboration.
set -euo pipefail

WORK="${1:-/tmp/stile-twitter-demo}"
rm -rf "$WORK"
mkdir -p "$WORK"

cat > "$WORK/task.md" <<'EOF'
# Refactor src/auth.py

## user
What's brittle here?
EOF

stile init "$WORK/task.md" --json >/dev/null
echo "ready: cd $WORK"
