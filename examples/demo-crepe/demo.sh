#!/usr/bin/env bash
# Multi-pane tmux demo: a brainstorming session on a stile-managed
# Markdown file. Three Claude-driven personas (cook, logistics, ux)
# plus a note-taker collaborate via the headless-agents.sh script;
# a tiny puppeteer drives Emacs to play the user.
#
# Layout:
#
#   +---------------------------------------------------------------+
#   |                                                               |
#   |    Emacs viewer of brainstorm.md (stile-mode + auto-revert)   |
#   |                                                               |
#   +-------------------------------+-------------------------------+
#   |  user (puppeteer typing)      |  agents (headless-agents log) |
#   +-------------------------------+-------------------------------+
#
# Live preview: ./demo.sh
# Recording:    vhs demo.tape
set -euo pipefail

DIR="$(cd "$(dirname "$0")" && pwd)"
WORK="${1:-/tmp/stile-crepe-demo}"
SESSION="${STILE_DEMO_SESSION:-stile-crepe-demo}"

command -v tmux   >/dev/null || { echo "tmux not on PATH" >&2; exit 2; }
command -v stile  >/dev/null || { echo "stile not on PATH (try: pip install -e cli/)" >&2; exit 2; }
command -v claude >/dev/null || { echo "claude not on PATH" >&2; exit 2; }
command -v emacs  >/dev/null || { echo "emacs not on PATH" >&2; exit 2; }

# Headless-agents script lives next to this file's parent.
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

# Top: real Emacs running stile-mode against brainstorm.md.
tmux send-keys -t "$viewer" \
    "clear; $ENV_PREFIX exec emacs -nw -Q -l '$DIR/demo-init.el' '$FILE'" Enter

# Bottom-right: headless-agents.sh with our four roles. Sonnet model
# (set in headless-agents.sh) keeps each turn snappy. STAGGER=3 puts
# successive agents about a Claude turn apart so each one usually
# sees the previous reply in the file.
tmux send-keys -t "$agents_pane" \
    "clear; $ENV_PREFIX exec '$HEADLESS' '$FILE' cook logistics ux-designer note-taker" Enter

# Bottom-left: puppeteer that types into Emacs as the user. Give Emacs
# a moment to come up first.
tmux send-keys -t "$user_pane" \
    "clear; $ENV_PREFIX exec python3 '$DIR/bg-user.py' '$viewer'" Enter

tmux set-option -t "$SESSION" status off
tmux attach-session -t "$SESSION"
