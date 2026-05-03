#!/usr/bin/env bash
# Spawn N headless Claude agents that collaborate with the user (and
# each other) on a shared file via `stile`. Each agent polls the file
# on a fixed interval, calls `claude --print -p ...` with the current
# file content, and submits the response through `stile save`. The
# 3-way merge serialises concurrent edits across actors.
#
# Usage:
#   ./headless-agents.sh FILE role1 [role2 ...]
#
# Example:
#   ./headless-agents.sh task.md reviewer linter tester
#
# Stops cleanly on Ctrl-C; spawned subshells exit when the parent dies.
#
# Dependencies on PATH: stile, claude, jq.
set -euo pipefail

if [[ $# -lt 2 ]]; then
    echo "usage: $0 FILE role1 [role2 ...]" >&2
    exit 2
fi

FILE="$1"; shift
ROLES=("$@")
INTERVAL="${INTERVAL:-5}"

for tool in stile claude jq; do
    command -v "$tool" >/dev/null || { echo "$tool not on PATH" >&2; exit 2; }
done

# Make the file managed by stile if it isn't already (idempotent).
[[ -f "$FILE" ]] || touch "$FILE"
stile init "$FILE" --json >/dev/null 2>&1 || true

# Per-role agent loop. Runs in a subshell so they're independent.
agent() {
    local role="$1"
    local last_sha=""
    while true; do
        local meta base_sha base_path proposed result mode

        meta=$(stile open "$FILE" --json) || { sleep "$INTERVAL"; continue; }
        base_sha=$(printf '%s' "$meta" | jq -r .base_sha)
        base_path=$(printf '%s' "$meta" | jq -r .base_path)

        # Skip cycle when nothing has changed -- avoids burning Claude
        # tokens on a file that hasn't moved.
        if [[ "$base_sha" == "$last_sha" ]]; then
            sleep "$INTERVAL"
            continue
        fi

        proposed=$(claude --print -p "$(printf 'You are agent:%s working in a Markdown file shared with a human user and other agents. The file is managed by stile (each save goes through a 3-way merge).\n\n- Read the entire current file.\n- If a `## user` block, or another agent, has added something that calls for your input AS %s, edit your `## agent:%s` section IN PLACE to respond. Replace the body, do not append.\n- If there is nothing new for you to do, output the file UNCHANGED.\n\nOutput ONLY the entire new file content. No preamble, no codefences around the file, no closing remarks.' "$role" "$role" "$role")" < "$base_path") || \
            { echo "[$role] claude failed" >&2; sleep "$INTERVAL"; continue; }

        result=$(printf '%s' "$proposed" | stile save "$FILE" \
            --base-sha "$base_sha" --actor "agent:$role" --json) || true
        mode=$(printf '%s' "$result" | jq -r '.mode // .status' 2>/dev/null || echo "??")
        printf '[%-12s] %s\n' "agent:$role" "$mode"

        last_sha=$base_sha
        sleep "$INTERVAL"
    done
}

# Background one agent per role; track PIDs so we can clean up on exit.
pids=()
for role in "${ROLES[@]}"; do
    agent "$role" &
    pids+=($!)
done
trap 'kill "${pids[@]}" 2>/dev/null || true' EXIT INT TERM

echo "${#ROLES[@]} agents running on $FILE -- Ctrl-C to stop." >&2
wait
