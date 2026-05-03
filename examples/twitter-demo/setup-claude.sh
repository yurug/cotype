#!/usr/bin/env bash
# Seed the working dir for the Claude collaborative-doc demo.
#
# Layout: a structured Markdown document with one heading per actor.
# The user owns `## requirements`; three agents own `## engineer`,
# `## tester`, `## marketer`. Each agent's body is initially a
# placeholder; they fill it in by reacting to the section they depend on:
#
#   engineer  reads `## requirements`   writes `## engineer`
#   tester    reads `## engineer`       writes `## tester`
#   marketer  reads `## engineer`       writes `## marketer`
#
# Different actors edit different sections, so concurrent saves are
# disjoint diffs that stile's `diff3 -m` merges cleanly. There is no
# trailing-append "chat" anywhere -- the document IS the workspace.
set -euo pipefail

WORK="${1:-/tmp/stile-twitter-demo}"
rm -rf "$WORK"
mkdir -p "$WORK"

cat > "$WORK/task.md" <<'EOF'
# 🚀 Tiny rocket build

## requirements

- fits in a backpack
- launches at least 50 m


## engineer

(no design yet -- waiting on requirements)


## tester

(no plan yet -- waiting on engineer)


## marketer

(no tagline yet -- waiting on engineer)
EOF

stile init "$WORK/task.md" --json >/dev/null
echo "ready: cd $WORK"
