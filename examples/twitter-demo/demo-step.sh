#!/usr/bin/env bash
# Run one agent pass and print a single tidy line.
# Usage: ./demo-step.sh <reviewer|linter|tester>
set -euo pipefail

role="$1"
DIR="$(cd "$(dirname "$0")" && pwd)"
RUNNER="$DIR/../agent-loop/run_agent.py"

# `run_agent.py` writes "save: <mode>" to stderr.  Capture combined and pull
# just that fragment so the demo line stays one column.
out=$(python3 "$RUNNER" task.md \
        --agent "$DIR/agents/${role}.py" \
        --actor "agent:${role}" 2>&1)
mode=$(echo "$out" | grep -oE 'save: [a-z]+' | head -1 || echo "save: ??")
printf '  agent:%-9s %s\n' "$role" "$mode"
