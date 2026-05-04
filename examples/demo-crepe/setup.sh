#!/usr/bin/env bash
# Idempotent setup for the crêpe-stand brainstorming demo.
# Wipes any prior workspace + sidecar so each run starts fresh, then
# pre-allocates the same section template `headless-agents.sh' would
# create on its own.
#
# We do this here (and not in `headless-agents.sh' alone) because the
# demo launches Emacs, headless-agents, and the puppeteer in parallel
# tmux panes. If Emacs were to read the file before headless-agents
# wrote the template, find-file-hook would run with no sidecar
# present, cotype-mode would not auto-enable, and the buffer would stay
# empty -- the puppeteer's `M-x cotype-demo-position-for-user' search
# would then fail and the typed message would land at point-min,
# *before* the `## user' header. Doing the prep here means both Emacs
# and headless-agents see a fully-initialised state from the start.
#
# Usage: ./setup.sh [WORKDIR]   (default: /tmp/cotype-crepe-demo)
set -euo pipefail

WORK="${1:-/tmp/cotype-crepe-demo}"
FILE="$WORK/brainstorm.md"
ROLES=(cook logistics ux-designer note-taker)

mkdir -p "$WORK"
rm -f "$FILE"
rm -rf "$(dirname "$FILE")/.$(basename "$FILE").cotype"

# Pre-allocate sections + per-role placeholders (must match the format
# in `examples/headless-agents.sh' so the script's own template check
# is a no-op when it starts).
{
    echo "## user"
    echo
    echo
    for role in "${ROLES[@]}"; do
        echo "## agent:$role"
        echo
        echo "_(no reply from $role yet)_"
        echo
    done
} > "$FILE"

# Initialise the sidecar so that when Emacs opens the file via
# find-file-hook -> cotype-maybe-enable, the sidecar already exists and
# cotype-mode (and auto-revert) auto-enable in the buffer.
cotype init "$FILE" --json >/dev/null 2>&1 || true

echo "$WORK"
