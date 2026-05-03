#!/usr/bin/env bash
# Live "editor" view for the top tmux pane: re-renders task.md every
# half-second. Designed to look like a buffer the user has open while
# agents save concurrently.
#
# Portability: uses only `clear`, `printf`, `cat`, `sleep` -- no
# `sha256sum` or other GNU-only utilities, so it runs unchanged on macOS.
# `set -euo pipefail` is intentionally OFF: a transient `cat` failure
# (during atomic-rename) must not collapse the pane mid-recording.

target="${1:-task.md}"
while true; do
    # Some terminals lack `clear`; fall back to ANSI cursor-home + erase.
    clear 2>/dev/null || printf '\033[H\033[J'
    printf '\033[1;36m─── %s ─── (your editor; stile-managed) ─\033[0m\n' "$target"
    cat "$target" 2>/dev/null || echo "(waiting for $target...)"
    sleep 0.5
done
