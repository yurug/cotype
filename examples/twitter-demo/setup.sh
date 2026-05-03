#!/usr/bin/env bash
# Prepare the working directory for the demo.
# Usage: ./setup.sh [WORKDIR]   (default: /tmp/stile-twitter-demo)
set -euo pipefail

WORK="${1:-/tmp/stile-twitter-demo}"
rm -rf "$WORK"
mkdir -p "$WORK"

cat > "$WORK/task.md" <<'EOF'
# Refactor src/auth.py

## user
What's brittle here?

---

## agent:reviewer

SLOT_REVIEWER

---

## agent:linter

SLOT_LINTER

---

## agent:tester

SLOT_TESTER
EOF

stile init "$WORK/task.md" --json >/dev/null
echo "ready: cd $WORK"
