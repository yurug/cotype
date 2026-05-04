#!/usr/bin/env bash
# Spawn N headless Claude agents that collaborate with the user (and
# each other) on a shared file via `stile`. Each agent polls the file
# on a fixed interval, calls `claude --print -p ...` with the current
# file content, and submits the response through `stile save`. The
# 3-way merge serialises concurrent edits across actors.
#
# Conflict-avoidance protocol (enforced -- not "please be careful"):
#   - On startup we pre-allocate `## user` plus one `## agent:<role>`
#     section per agent (each with a unique placeholder body), so the
#     file structure exists from cycle 0.
#   - After Claude returns its take on the whole file, we DO NOT trust
#     it byte-for-byte. We parse out only the agent's own section body
#     and splice it back into the bytes we read from `base_path`. Every
#     byte outside the agent's section is, by construction, identical
#     to what stile captured as the base. Two agents editing two
#     different sections therefore cannot produce a 3-way conflict.
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
INTERVAL="${INTERVAL:-1}"
# Defaults to Sonnet for snappier turns; override with `CLAUDE_MODEL=...`
# (e.g. `claude-haiku-4-5-20251001` for max speed, or unset/empty to let
# the claude CLI pick its own default).
CLAUDE_MODEL="${CLAUDE_MODEL:-claude-sonnet-4-6}"

for tool in stile claude jq python3; do
    command -v "$tool" >/dev/null || { echo "$tool not on PATH" >&2; exit 2; }
done

# Make the file managed by stile if it isn't already (idempotent).
[[ -f "$FILE" ]] || touch "$FILE"

# Pre-allocate section headers + a unique per-role placeholder body when
# FILE is empty. The placeholders give diff3 unique unchanged lines as
# anchors around each section (so concurrent edits to two different
# agent sections can't get grouped into one diff3 region) and give the
# agent prompt a clear "replace this exact line" target.
if ! [[ -s "$FILE" ]]; then
    {
        echo "## user"
        echo
        echo
        for role in "${ROLES[@]}"; do
            echo "## agent:$role"
            echo
            echo "_(no reply from $role yet)_"
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
        prompt="You are agent:$role collaborating with a human user and other agents on a shared Markdown file. Each participant owns exactly ONE section: \`## user\`, \`## agent:$role\`, and one \`## agent:<other>\` per other agent.

Your section is \`## agent:$role\`. Its body initially contains a placeholder line; when you have something to say AS $role, replace the placeholder (or your previous reply) with your new reply.

You can ignore the contents of the OTHER \`## agent:<other>\` sections in your output -- the harness will splice ONLY your own section's body back into the file. Anything you write outside \`## agent:$role\`'s body will be discarded.

If neither the user nor another agent has asked for your input AS $role since your last reply, leave \`## agent:$role\`'s body unchanged.

Output the entire file (it's the simplest format), no preamble, no code fences, no commentary.

<file>
$file_content
</file>"
        local tmp_claude tmp_spliced
        tmp_claude=$(mktemp -t stile-claude.XXXXXX)
        tmp_spliced=$(mktemp -t stile-spliced.XXXXXX)
        # shellcheck disable=SC2064
        trap "rm -f '$tmp_claude' '$tmp_spliced'" RETURN

        local -a claude_args=(--print -p "$prompt")
        [[ -n "$CLAUDE_MODEL" ]] && claude_args+=(--model "$CLAUDE_MODEL")
        if ! claude "${claude_args[@]}" > "$tmp_claude"; then
            echo "[$role] claude failed" >&2
            rm -f "$tmp_claude" "$tmp_spliced"
            sleep "$INTERVAL"
            continue
        fi

        # Skip if Claude returned nothing useful (avoids zero-byte saves
        # that would empty the file).
        if [[ -z "$(tr -d '[:space:]' < "$tmp_claude")" ]]; then
            printf '[%-12s] empty response, skipped\n' "agent:$role"
            rm -f "$tmp_claude" "$tmp_spliced"
            last_sha=$base_sha
            sleep "$INTERVAL"
            continue
        fi

        # Splice ONLY the agent's section body from Claude's output back
        # into the bytes we read from base_path. Exit codes:
        #   0  -> tmp_spliced contains the new file content (real change)
        #   42 -> no semantic change (skip the save)
        #   1  -> splice error (Claude returned malformed structure)
        local splice_rc=0
        python3 - "$base_path" "$tmp_claude" "$tmp_spliced" "$role" <<'PYEOF' || splice_rc=$?
import sys

base_path, claude_path, out_path, role = sys.argv[1:5]
hdr = f"## agent:{role}".encode("utf-8")

def split_sections(b: bytes) -> list[list[bytes]]:
    """Split bytes into sections. A section is a list of lines starting
    with a `## ` header line; a leading 'preamble' (lines before the first
    `## `) becomes the first section."""
    sections: list[list[bytes]] = []
    current: list[bytes] = []
    for line in b.split(b"\n"):
        if line.startswith(b"## "):
            if current:
                sections.append(current)
            current = [line]
        else:
            current.append(line)
    if current:
        sections.append(current)
    return sections

def join_sections(secs: list[list[bytes]]) -> bytes:
    return b"\n".join(b"\n".join(s) for s in secs)

with open(base_path, "rb") as f:
    base = f.read()
with open(claude_path, "rb") as f:
    claude_out = f.read()

# Strip a single layer of ``` ... ``` if Claude wrapped the whole file.
stripped = claude_out.strip()
if stripped.startswith(b"```") and stripped.endswith(b"```"):
    inner = stripped[3:-3]
    nl = inner.find(b"\n")
    if nl >= 0:
        claude_out = inner[nl + 1:]

base_secs = split_sections(base)
claude_secs = split_sections(claude_out)

base_body = next((s[1:] for s in base_secs if s and s[0] == hdr), None)
claude_body = next((s[1:] for s in claude_secs if s and s[0] == hdr), None)

if base_body is None:
    sys.stderr.write(f"section {hdr.decode()} missing in base file\n")
    sys.exit(1)
if claude_body is None or claude_body == base_body:
    sys.exit(42)

out_secs = [
    ([s[0]] + claude_body) if (s and s[0] == hdr) else s
    for s in base_secs
]
with open(out_path, "wb") as f:
    f.write(join_sections(out_secs))
sys.exit(0)
PYEOF
        case "$splice_rc" in
            0) ;;  # fall through to save
            42)
                printf '[%-12s] no change in own section, skipped\n' "agent:$role"
                rm -f "$tmp_claude" "$tmp_spliced"
                last_sha=$base_sha
                sleep "$INTERVAL"
                continue
                ;;
            *)
                printf '[%-12s] splice failed (rc=%s)\n' "agent:$role" "$splice_rc"
                rm -f "$tmp_claude" "$tmp_spliced"
                last_sha=$base_sha
                sleep "$INTERVAL"
                continue
                ;;
        esac

        result=$(stile save "$FILE" \
            --base-sha "$base_sha" --actor "agent:$role" --json \
            < "$tmp_spliced") || true
        rm -f "$tmp_claude" "$tmp_spliced"

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
