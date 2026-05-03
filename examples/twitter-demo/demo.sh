#!/usr/bin/env bash
# Multi-pane tmux demo: live "editor view" of task.md on top, three
# real agent processes at the bottom each running stile open / save in
# parallel. Run live in your terminal to preview, or record with
# `vhs demo.tape`.
set -euo pipefail

DIR="$(cd "$(dirname "$0")" && pwd)"
WORK="${1:-/tmp/stile-twitter-demo}"
SESSION="${STILE_DEMO_SESSION:-stile-tmux-demo}"

# tmux must be installed; stile must be on PATH.
command -v tmux >/dev/null || { echo "tmux not on PATH" >&2; exit 2; }
command -v stile >/dev/null || { echo "stile not on PATH (try: pip install -e cli/)" >&2; exit 2; }

# Fresh slate: kill any prior session, re-seed the working dir.
tmux kill-session -t "$SESSION" 2>/dev/null || true
"$DIR/setup.sh" "$WORK" >/dev/null

# tmux runs each pane's command via `$SHELL -c`. The -e overrides below
# neutralise the user's zsh/bash startup files so a noisy .zshenv (e.g.
# one that calls oh-my-zsh's `git_prompt_info` from a shared config and
# fails under bash) cannot kill the pane before the script even runs.
# Setting ZDOTDIR=/dev/null tells zsh to look for rc files in /dev/null;
# BASH_ENV/ENV empty disables non-interactive bash sourcing.
TMUX_ENV=(
    -e "ZDOTDIR=/dev/null"
    -e "BASH_ENV="
    -e "ENV="
)

# Top pane: live editor view of task.md, full width.
tmux new-session -d -s "$SESSION" -c "$WORK" -x 180 -y 50 \
    "${TMUX_ENV[@]}" \
    "$DIR/bg-viewer.sh task.md"

# Bottom row, 14 rows tall, three equal-width agent panes.
tmux split-window -t "$SESSION:0.0" -v -l 14  -c "$WORK" \
    "${TMUX_ENV[@]}" "python3 $DIR/bg-agent.py reviewer"
tmux split-window -t "$SESSION:0.1" -h -l 105 -c "$WORK" \
    "${TMUX_ENV[@]}" "python3 $DIR/bg-agent.py linter"
tmux split-window -t "$SESSION:0.2" -h -l 52  -c "$WORK" \
    "${TMUX_ENV[@]}" "python3 $DIR/bg-agent.py tester"

# Cosmetic: drop the status bar so the recording is uncluttered.
tmux set-option -t "$SESSION" status off

tmux attach-session -t "$SESSION"
