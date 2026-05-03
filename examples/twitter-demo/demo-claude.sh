#!/usr/bin/env bash
# Multi-round, claude-driven Twitter demo.
#
# Layout (5 panes total):
#
#   +--------------------------------------------------+
#   |                                                  |
#   |              Emacs (your editor)                 |
#   |              -- stile-mode active --             |
#   |                                                  |
#   +-------+--------------+-------------+-------------+
#   | user  | agent:code   | agent:tests | agent:docs  |
#   +-------+--------------+-------------+-------------+
#
# The bottom-left "user" pane runs bg-puppeteer.py, which simulates a
# human: it M-x's a small Emacs helper to position point in `## spec`,
# then types the new bullet character-by-character, then C-x C-s. The
# three agents (`bg-claude.py code|tests|docs`) poll task.md and
# regenerate the body of the section they own when their dependency
# changes.
#
# `claude` CLI is required for real LLM responses; without it the
# agents fall back to canned bodies (STILE_DEMO_FAKE_CLAUDE=1).
set -euo pipefail

DIR="$(cd "$(dirname "$0")" && pwd)"
WORK="${1:-/tmp/stile-twitter-demo}"
SESSION="${STILE_DEMO_SESSION:-stile-claude-demo}"

command -v tmux >/dev/null || { echo "tmux not on PATH" >&2; exit 2; }
command -v stile >/dev/null || { echo "stile not on PATH (try: pip install -e cli/)" >&2; exit 2; }

if ! command -v claude >/dev/null 2>&1; then
    echo "note: claude CLI not on PATH; agents will use canned responses" >&2
    export STILE_DEMO_FAKE_CLAUDE=1
fi

tmux kill-session -t "$SESSION" 2>/dev/null || true
"$DIR/setup-claude.sh" "$WORK" >/dev/null

# Capture pane IDs (immune to base-index / pane-base-index settings).
# Pane geometry tuned for a 180-col session: bottom row = 14 rows tall;
# four bottom panes are ~32, 49, 49, 50 cols (user is the narrowest).
viewer=$(tmux new-session -d -s "$SESSION" -c "$WORK" -x 180 -y 50 \
    -P -F "#{pane_id}")
user_pane=$(tmux split-window -v -t "$viewer"     -l 14  -c "$WORK" \
    -P -F "#{pane_id}")
agent_c=$(tmux split-window -h -t "$user_pane" -l 50 -c "$WORK" \
    -P -F "#{pane_id}")
agent_b=$(tmux split-window -h -t "$user_pane" -l 49 -c "$WORK" \
    -P -F "#{pane_id}")
agent_a=$(tmux split-window -h -t "$user_pane" -l 49 -c "$WORK" \
    -P -F "#{pane_id}")
# Geometry now: user_pane (~32 cols) | agent_a (49) | agent_b (49) | agent_c (50)

# Top pane viewer: real Emacs running stile-mode, fallback to bg-viewer.sh
if command -v emacs >/dev/null 2>&1; then
    VIEWER_CMD="exec emacs -nw -Q -l '$DIR/demo-init.el' task.md"
else
    echo "note: emacs not on PATH; falling back to bg-viewer.sh" >&2
    VIEWER_CMD="exec '$DIR/bg-viewer.sh' task.md"
fi

ENV_PREFIX='ZDOTDIR=/dev/null BASH_ENV= ENV='
if [[ "${STILE_DEMO_FAKE_CLAUDE:-}" ]]; then
    ENV_PREFIX="$ENV_PREFIX STILE_DEMO_FAKE_CLAUDE=1"
fi

tmux send-keys -t "$viewer"    "clear; $ENV_PREFIX $VIEWER_CMD" Enter
tmux send-keys -t "$user_pane" "clear; $ENV_PREFIX exec python3 '$DIR/bg-puppeteer.py' '$viewer'" Enter
tmux send-keys -t "$agent_a"   "clear; $ENV_PREFIX exec python3 '$DIR/bg-claude.py' code"  Enter
tmux send-keys -t "$agent_b"   "clear; $ENV_PREFIX exec python3 '$DIR/bg-claude.py' tests" Enter
tmux send-keys -t "$agent_c"   "clear; $ENV_PREFIX exec python3 '$DIR/bg-claude.py' docs"  Enter

tmux set-option -t "$SESSION" status off
tmux attach-session -t "$SESSION"
