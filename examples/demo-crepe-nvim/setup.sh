#!/usr/bin/env bash
# Idempotent setup for the cotype crêpe-stand demo (neovim variant).
# Wipes any prior workspace + sidecar so each run starts fresh, then
# pre-allocates the same section template `headless-agents.sh' would
# create on its own.
#
# We do this here (and not in `headless-agents.sh' alone) because the
# demo launches nvim, headless-agents, and the puppeteer in parallel
# tmux panes. If nvim were to read the file before headless-agents
# wrote the template, the cotype plugin's BufReadPost auto-enable would
# run with no sidecar present and the buffer would stay empty -- the
# puppeteer's `:CotypeDemoPositionForUser' search would then fail and
# the typed message would land in random parts of the buffer.
#
# Doing the prep here means both nvim and headless-agents see a fully
# initialised state from the start.
#
# Usage: ./setup.sh [WORKDIR]   (default: /tmp/cotype-crepe-nvim-demo)
set -euo pipefail

WORK="${1:-/tmp/cotype-crepe-nvim-demo}"
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

# Initialise the sidecar so that when nvim opens the file, the cotype
# plugin's BufReadPost auto-enable hook sees it and turns on cotype-mode
# (and auto-revert) for the buffer.
cotype init "$FILE" --json >/dev/null 2>&1 || true

echo "$WORK"
