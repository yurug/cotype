#!/usr/bin/env bash
# Live "editor" view for the top tmux pane: re-renders task.md whenever
# its content hash changes. Designed to look like a buffer the user has
# open while agents save concurrently.
set -euo pipefail

target="${1:-task.md}"
last=""
while true; do
    if [[ -f "$target" ]]; then
        cur=$(sha256sum "$target" | cut -d' ' -f1)
        if [[ "$cur" != "$last" ]]; then
            clear
            printf '\033[1;36m─── %s ─── (your editor; stile-managed) ─\033[0m\n' "$target"
            cat "$target"
            last="$cur"
        fi
    fi
    sleep 0.25
done
