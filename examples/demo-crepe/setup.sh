#!/usr/bin/env bash
# Idempotent setup for the crêpe-stand brainstorming demo.
# Wipes any prior workspace + sidecar so each run starts fresh.
#
# Usage: ./setup.sh [WORKDIR]   (default: /tmp/stile-crepe-demo)
set -euo pipefail

WORK="${1:-/tmp/stile-crepe-demo}"
FILE="$WORK/brainstorm.md"

mkdir -p "$WORK"
rm -f "$FILE"
rm -rf "$(dirname "$FILE")/.$(basename "$FILE").stile"
touch "$FILE"

echo "$WORK"
