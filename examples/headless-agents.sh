#!/usr/bin/env bash
# Spawn N headless Claude agents that collaborate with the user (and
# each other) on a shared file via `stile`. Each agent polls the file
# on a fixed interval, calls `claude --print -p ...` with the current
# file content, and submits the response through `stile save`. The
# 3-way merge serialises concurrent edits across actors.
#
# Conflict-avoidance protocol (best-effort, not enforced):
#   - On startup we pre-allocate `## user` and one `## agent:<role>`
#     header per agent, separated by a blank line. This gives diff3
#     stable anchors so two simultaneous saves don't end up appending
#     adjacent text at end-of-file (the worst case for diff3).
#   - The prompt tells each agent it owns ONLY its `## agent:<role>`
#     section's body and must preserve every other byte verbatim.
#   - Agent startup is staggered across the polling INTERVAL so the N
#     agents fire on N different phases instead of all on the same tick.
#
# When `stile save` produces a conflict despite all that, the file gets
# diff3-style `<<<<<<<` / `>>>>>>>` markers. While markers are present,
# agents stop calling Claude -- the user is expected to edit FILE in
# their editor and run `stile resolve FILE`. Agents resume automatically
# once resolve clears the pending state.
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

# Pre-allocate section headers when FILE is empty. With every section
# header already present (separated by blank lines), each agent's edit
# lands inside its own pre-existing slot rather than appending at EOF
# next to every other agent's append -- which is diff3's worst case.
if ! [[ -s "$FILE" ]]; then
    {
        echo "## user"
        echo
        for role in "${ROLES[@]}"; do
            echo "## agent:$role"
            echo
        done
    } > "$FILE"
fi

stile init "$FILE" --json >/dev/null 2>&1 || true

print_conflict_hint() {
    cat >&2 <<EOF
[stile] $FILE has a pending conflict.
Edit the file to remove the <<<<<<< / ======= / >>>>>>> markers, then run:
    stile resolve "$FILE"
Agents will resume automatically once the conflict clears.
EOF
}

# Per-role agent loop. Runs in a subshell so each role is independent.
# `idx` and `total` are used only for the startup stagger.
agent() {
    local role="$1"
    local idx="$2"
    local total="$3"
    local last_sha=""

    # Stagger startup phase: agent N of M sleeps (N * INTERVAL / M)
    # seconds before its first iteration. With 3 agents at 5s interval
    # this puts them on phases 0s, ~1.67s, ~3.33s instead of all
    # firing on the same 0s/5s/10s ticks.
    local stagger
    stagger=$(awk "BEGIN { printf \"%.3f\", $idx * $INTERVAL / $total }")
    sleep "$stagger"

    while true; do
        # Idle while a conflict is pending: no save can succeed and the
        # user is the only actor who can resolve it. Saves Claude calls.
        local s
        s=$(stile status "$FILE" --json 2>/dev/null | jq -r '.status // "??"')
        if [[ "$s" == "conflicted" ]]; then
            sleep "$INTERVAL"
            continue
        fi

        local meta base_sha base_path proposed result
        meta=$(stile open "$FILE" --json) || { sleep "$INTERVAL"; continue; }
        base_sha=$(printf '%s' "$meta" | jq -r .base_sha)
        base_path=$(printf '%s' "$meta" | jq -r .base_path)

        # Skip cycle when nothing has changed -- avoids burning Claude
        # tokens on a file that hasn't moved.
        if [[ "$base_sha" == "$last_sha" ]]; then
            sleep "$INTERVAL"
            continue
        fi

        # `claude --print -p PROMPT` does NOT read stdin -- splice the
        # current file content into the prompt directly, between <file> tags.
        local file_content
        file_content=$(cat "$base_path")
        local prompt
        prompt="You are agent:$role collaborating with a human user and other agents on a shared Markdown file managed by stile (which 3-way-merges concurrent saves).

PROTOCOL (follow byte-exactly to avoid merge conflicts):
1. Your section is \`## agent:$role\`. You may edit ONLY the body of that section (the lines between its header and the next \`## \` header, or end-of-file).
2. Every other byte of the file -- the \`## user\` header and body, every other \`## agent:<role>\` header and body, every blank line and every space -- MUST be preserved byte-for-byte. Do NOT reformat, reorder, fix typos, normalise whitespace, add or remove blank lines, or change anything outside your own section's body.
3. If the user or another agent has not asked for your input AS $role since your last reply, output the file UNCHANGED, byte-for-byte.

Output ONLY the entire new file content. No preamble, no code fences, no commentary.

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

        local status mode err msg cid
        status=$(printf '%s' "$result" | jq -r '.status // "??"')
        case "$status" in
            saved)
                mode=$(printf '%s' "$result" | jq -r '.mode')
                printf '[%-12s] save: %s\n' "agent:$role" "$mode"
                ;;
            conflict)
                cid=$(printf '%s' "$result" | jq -r '.conflict_id')
                printf '[%-12s] conflict %s -- markers written to %s\n' \
                    "agent:$role" "${cid:0:8}" "$FILE"
                print_conflict_hint
                ;;
            error)
                err=$(printf '%s' "$result" | jq -r '.error')
                msg=$(printf '%s' "$result" | jq -r '.message')
                printf '[%-12s] error: %s -- %s\n' "agent:$role" "$err" "$msg"
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
total=${#ROLES[@]}
for i in "${!ROLES[@]}"; do
    role="${ROLES[$i]}"
    agent "$role" "$i" "$total" &
    pids+=($!)
done
trap 'kill "${pids[@]}" 2>/dev/null || true' EXIT INT TERM

echo "${#ROLES[@]} agents running on $FILE -- Ctrl-C to stop." >&2
wait
