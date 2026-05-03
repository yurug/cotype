#!/usr/bin/env bash
# Multi-pane tmux demo: live "editor view" of task.md on top, three
# real agent processes at the bottom each running stile open / save in
# parallel. Run live in your terminal to preview, or record with
# `vhs demo.tape`.
#
# Implementation notes:
# - Pane IDs (%1, %2, ...) are captured via -P -F "#{pane_id}" because
#   numeric indices depend on the user's base-index / pane-base-index
#   settings; pane IDs do not.
# - Panes are created without commands; commands are sent via send-keys
#   AFTER all four panes exist, so a failing command can never collapse
#   the window before the layout is built.
# - `exec` replaces the shell with the script, so the user only sees
#   the briefest flash of their default shell prompt before the
#   recording-friendly content takes over.
set -euo pipefail

DIR="$(cd "$(dirname "$0")" && pwd)"
WORK="${1:-/tmp/stile-demo}"
SESSION="${STILE_DEMO_SESSION:-stile-tmux-demo}"

command -v tmux >/dev/null || { echo "tmux not on PATH" >&2; exit 2; }
command -v stile >/dev/null || { echo "stile not on PATH (try: pip install -e cli/)" >&2; exit 2; }

tmux kill-session -t "$SESSION" 2>/dev/null || true
"$DIR/setup.sh" "$WORK" >/dev/null

# Layout (geometry tuned for a -x 180 -y 50 client):
#
#   +-----------------------+   viewer  (full width, ~36 rows)
#   |                       |
#   +-------+-------+-------+   agent_a | agent_b | agent_c  (~14 rows)
#
viewer=$(tmux new-session -d -s "$SESSION" -c "$WORK" -x 180 -y 50 \
    -P -F "#{pane_id}")
agent_a=$(tmux split-window -v -t "$viewer"  -l 14  -c "$WORK" \
    -P -F "#{pane_id}")
agent_b=$(tmux split-window -h -t "$agent_a" -l 120 -c "$WORK" \
    -P -F "#{pane_id}")
agent_c=$(tmux split-window -h -t "$agent_b" -l 60  -c "$WORK" \
    -P -F "#{pane_id}")

# Pick the viewer: real Emacs running `stile-mode' if available (matches
# what the project actually ships), else the plain `bg-viewer.sh' loop.
if command -v emacs >/dev/null 2>&1; then
    VIEWER_CMD="exec emacs -nw -Q -l '$DIR/demo-init.el' task.md"
else
    echo "note: emacs not found on PATH; falling back to bg-viewer.sh" >&2
    VIEWER_CMD="exec '$DIR/bg-viewer.sh' task.md"
fi

# Wire commands. The inline env (ZDOTDIR/BASH_ENV/ENV) belongs to the
# `exec`-spawned process, not the outer shell that already sourced rc;
# it shouldn't matter for our scripts but is cheap insurance.
ENV_PREFIX='ZDOTDIR=/dev/null BASH_ENV= ENV='
tmux send-keys -t "$viewer" \
    "clear; $ENV_PREFIX $VIEWER_CMD" Enter
tmux send-keys -t "$agent_a" \
    "clear; $ENV_PREFIX exec python3 '$DIR/bg-agent.py' reviewer" Enter
tmux send-keys -t "$agent_b" \
    "clear; $ENV_PREFIX exec python3 '$DIR/bg-agent.py' linter" Enter
tmux send-keys -t "$agent_c" \
    "clear; $ENV_PREFIX exec python3 '$DIR/bg-agent.py' tester" Enter

tmux set-option -t "$SESSION" status off
tmux attach-session -t "$SESSION"
