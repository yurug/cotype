#!/usr/bin/env bash
# Multi-pane tmux demo: a brainstorming session on a cotype-managed
# Markdown file, with **neovim** as the user's editor (instead of the
# Emacs version in ../demo-crepe). Three Claude-driven personas plus a
# note-taker collaborate via the headless-agents.sh script; a tiny
# puppeteer drives nvim to play the user.
#
# Layout:
#
#   +----------------------------------------------------------------+
#   |                                                                |
#   |  neovim viewer of brainstorm.md (cotype-mode + auto-revert)    |
#   |                                                                |
#   +-------------------------------+--------------------------------+
#   |  user (puppeteer typing)      |  agents (headless-agents log)  |
#   +-------------------------------+--------------------------------+
#
# Live preview: ./demo.sh
# Recording:    vhs demo.tape
set -euo pipefail

DIR="$(cd "$(dirname "$0")" && pwd)"
WORK="${1:-/tmp/cotype-crepe-nvim-demo}"
SESSION="${COTYPE_DEMO_SESSION:-cotype-crepe-nvim-demo}"

command -v tmux   >/dev/null || { echo "tmux not on PATH" >&2; exit 2; }
command -v cotype >/dev/null || { echo "cotype not on PATH (try: pip install cotype)" >&2; exit 2; }
command -v claude >/dev/null || { echo "claude not on PATH" >&2; exit 2; }
command -v nvim   >/dev/null || { echo "nvim not on PATH" >&2; exit 2; }

# Headless-agents script lives next to this file's grandparent.
HEADLESS="$DIR/../headless-agents.sh"
[[ -x "$HEADLESS" ]] || { echo "missing or unexecutable: $HEADLESS" >&2; exit 2; }

tmux kill-session -t "$SESSION" 2>/dev/null || true
"$DIR/setup.sh" "$WORK" >/dev/null

FILE="$WORK/brainstorm.md"

# Capture pane IDs (immune to base-index settings). Layout:
#   viewer  (full width, ~36 rows)
#   user (left, ~90 cols) | agents (right, ~90 cols)   -- 14 rows tall
viewer=$(tmux new-session -d -s "$SESSION" -c "$WORK" -x 180 -y 50 \
    -P -F "#{pane_id}")
user_pane=$(tmux split-window -v -t "$viewer" -l 14 -c "$WORK" \
    -P -F "#{pane_id}")
agents_pane=$(tmux split-window -h -t "$user_pane" -l 90 -c "$WORK" \
    -P -F "#{pane_id}")

ENV_PREFIX='ZDOTDIR=/dev/null BASH_ENV= ENV='

# Top: neovim with the demo init. `-i NONE' suppresses ShaDa so each
# run starts from a clean state.
tmux send-keys -t "$viewer" \
    "clear; $ENV_PREFIX exec nvim -u '$DIR/demo-init.vim' -i NONE '$FILE'" Enter

# Bottom-right: headless-agents.sh with our four roles. Sonnet model
# (default in headless-agents.sh) keeps each turn snappy. STAGGER=3 puts
# successive agents about a Claude turn apart so each one usually sees
# the previous reply in the file.
tmux send-keys -t "$agents_pane" \
    "clear; $ENV_PREFIX exec '$HEADLESS' '$FILE' cook logistics ux-designer note-taker" Enter

# Bottom-left: puppeteer that types into nvim as the user. Give nvim a
# moment to come up first.
tmux send-keys -t "$user_pane" \
    "clear; $ENV_PREFIX exec python3 '$DIR/bg-user.py' '$viewer'" Enter

tmux set-option -t "$SESSION" status off
tmux attach-session -t "$SESSION"
