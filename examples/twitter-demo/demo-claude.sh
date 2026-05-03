#!/usr/bin/env bash
# Multi-round, claude-driven Twitter demo.
#
# Layout: real Emacs (top) + three polling Claude agents (bottom). A
# background "puppeteer" types user follow-ups into Emacs at scripted
# times (see bg-puppeteer.py), so the recording shows real ping-pong:
#
#   round 1: agents respond to the seeded ## user question
#   round 2: puppeteer types a follow-up, agents respond again
#   round 3: puppeteer types a wrap-up, agents wrap
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
viewer=$(tmux new-session -d -s "$SESSION" -c "$WORK" -x 180 -y 50 \
    -P -F "#{pane_id}")
agent_a=$(tmux split-window -v -t "$viewer"  -l 14  -c "$WORK" \
    -P -F "#{pane_id}")
agent_b=$(tmux split-window -h -t "$agent_a" -l 120 -c "$WORK" \
    -P -F "#{pane_id}")
agent_c=$(tmux split-window -h -t "$agent_b" -l 60  -c "$WORK" \
    -P -F "#{pane_id}")

# Top pane viewer: real Emacs running stile-mode, fallback to bg-viewer.sh
if command -v emacs >/dev/null 2>&1; then
    VIEWER_CMD="exec emacs -nw -Q -l '$DIR/demo-init.el' task.md"
else
    echo "note: emacs not on PATH; falling back to bg-viewer.sh" >&2
    VIEWER_CMD="exec '$DIR/bg-viewer.sh' task.md"
fi

ENV_PREFIX='ZDOTDIR=/dev/null BASH_ENV= ENV='
# Pass through STILE_DEMO_FAKE_CLAUDE if set, so the agent panes inherit it.
if [[ "${STILE_DEMO_FAKE_CLAUDE:-}" ]]; then
    ENV_PREFIX="$ENV_PREFIX STILE_DEMO_FAKE_CLAUDE=1"
fi

tmux send-keys -t "$viewer"  "clear; $ENV_PREFIX $VIEWER_CMD" Enter
tmux send-keys -t "$agent_a" "clear; $ENV_PREFIX exec python3 '$DIR/bg-claude.py' engineer" Enter
tmux send-keys -t "$agent_b" "clear; $ENV_PREFIX exec python3 '$DIR/bg-claude.py' tester"   Enter
tmux send-keys -t "$agent_c" "clear; $ENV_PREFIX exec python3 '$DIR/bg-claude.py' marketer" Enter

# Background puppeteer drives Emacs; logs to a file (not a pane) so the
# 4-pane layout stays clean.
( python3 "$DIR/bg-puppeteer.py" "$viewer" >"/tmp/stile-puppeteer.log" 2>&1 ) &
puppeteer_pid=$!
trap 'kill $puppeteer_pid 2>/dev/null || true' EXIT

tmux set-option -t "$SESSION" status off
tmux attach-session -t "$SESSION"
