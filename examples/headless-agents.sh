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

# Sidecar path next to FILE -- used in conflict-recovery messages.
sidecar_dir() {
    local f="$1"
    printf '%s/.%s.stile' "$(dirname "$f")" "$(basename "$f")"
}

print_conflict_recovery() {
    local cid="${1:-}"
    cat >&2 <<EOF
A pending conflict on $FILE blocks every save.
Recover by ONE of:
  - resolve it (after hand-editing the merged file):
      stile resolve "$FILE" --use-merged
  - or wipe the sidecar to start fresh (drops base history):
      rm -rf "$(sidecar_dir "$FILE")"
EOF
    [[ -n "$cid" ]] && echo "Pending conflict id: $cid" >&2
}

# Refuse to start if a conflict is already pending -- otherwise every
# agent will burn Claude calls on saves that can never succeed.
init_status=$(stile status "$FILE" --json)
if [[ "$(printf '%s' "$init_status" | jq -r .status)" == "conflicted" ]]; then
    cid=$(printf '%s' "$init_status" | jq -r '.pending_conflict.id')
    print_conflict_recovery "$cid"
    exit 5
fi

# Race-safe one-shot lock: the first agent to win `mkdir $LOCK_DIR/announced`
# prints recovery instructions; the others stay quiet.
LOCK_DIR=$(mktemp -d -t stile-headless.XXXXXX)
PARENT_PID=$$

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

        # Build the prompt with the file content embedded between
        # <file> tags. `claude --print -p PROMPT` does NOT read stdin --
        # the prompt argument is the entire input, so we have to splice
        # the current file content into it ourselves.
        local file_content
        file_content=$(cat "$base_path")
        local prompt
        prompt="You are agent:$role working in a Markdown file shared with a human user and other agents. The file is managed by stile (each save goes through a 3-way merge).

- Read the entire current file shown below.
- If a \`## user\` block, or another agent, has added something that calls for your input AS $role, edit (or append) a \`## agent:$role\` section to respond. If the section already exists, REPLACE its body in place; if it doesn't yet exist, append a new \`## agent:$role\` section AFTER all existing sections.
- If there is nothing new for you to do, output the file UNCHANGED.

Output ONLY the entire new file content. No preamble, no codefences around the whole file, no closing remarks.

<file>
$file_content
</file>"
        proposed=$(claude --print -p "$prompt") || \
            { echo "[$role] claude failed" >&2; sleep "$INTERVAL"; continue; }

        # Defensively strip a single layer of ``` ... ``` if Claude
        # wrapped the whole file (it sometimes does even when told not to).
        if [[ "$proposed" == '```'* && "$proposed" == *'```' ]]; then
            proposed=$(printf '%s' "$proposed" | sed -e '1d' -e '$d')
        fi

        # Skip if Claude returned nothing useful (avoids zero-byte saves
        # that would empty the file).
        if [[ -z "$(printf '%s' "$proposed" | tr -d '[:space:]')" ]]; then
            printf '[%-12s] empty response, skipped\n' "agent:$role"
            last_sha=$base_sha
            sleep "$INTERVAL"
            continue
        fi

        result=$(printf '%s' "$proposed" | stile save "$FILE" \
            --base-sha "$base_sha" --actor "agent:$role" --json) || true

        local status mode err msg
        status=$(printf '%s' "$result" | jq -r '.status // "??"')
        case "$status" in
            saved)
                mode=$(printf '%s' "$result" | jq -r '.mode')
                printf '[%-12s] save: %s\n' "agent:$role" "$mode"
                ;;
            conflict)
                cid=$(printf '%s' "$result" | jq -r '.conflict_id')
                printf '[%-12s] conflict %s -- run `stile resolve %s --use-merged` after editing\n' \
                    "agent:$role" "${cid:0:8}" "$FILE"
                ;;
            error)
                err=$(printf '%s' "$result" | jq -r '.error')
                msg=$(printf '%s' "$result" | jq -r '.message')
                printf '[%-12s] error: %s -- %s\n' "agent:$role" "$err" "$msg"
                if [[ "$err" == "ConflictPending" ]]; then
                    # Stop the whole script: every save will fail until
                    # the user resolves or wipes the sidecar.
                    if mkdir "$LOCK_DIR/announced" 2>/dev/null; then
                        print_conflict_recovery
                    fi
                    kill -TERM "$PARENT_PID" 2>/dev/null || true
                    return 0
                fi
                ;;
            *)
                printf '[%-12s] unexpected: %s\n' "agent:$role" "$result"
                ;;
        esac

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
trap 'kill "${pids[@]}" 2>/dev/null || true; rm -rf "$LOCK_DIR"' EXIT INT TERM

echo "${#ROLES[@]} agents running on $FILE -- Ctrl-C to stop." >&2
wait
