#!/usr/bin/env bash
# Seed the working dir for the Claude collaborative-doc demo.
#
# A short concrete programming task: design `sum_evens(xs)` together.
# User owns `## spec` (the requirements). Three agents own one section
# each and react to the section they depend on:
#
#   code    reads `## spec`   writes `## code`     (the implementation)
#   tests   reads `## code`   writes `## tests`    (the assertions)
#   docs    reads `## code`   writes `## docs`     (the docstring)
#
# Different actors edit different sections, so concurrent saves are
# disjoint diffs that stile's `diff3 -m` merges cleanly. There is no
# trailing-append "chat" anywhere -- the document IS the workspace.
set -euo pipefail

WORK="${1:-/tmp/stile-twitter-demo}"
rm -rf "$WORK"
mkdir -p "$WORK"

cat > "$WORK/task.md" <<'EOF'
# `sum_evens(xs)` — a tiny collaborative function

## spec

- Given a list of integers, return the sum of the even ones.


## code

(no implementation yet -- waiting on spec)


## tests

(no tests yet -- waiting on code)


## docs

(no docstring yet -- waiting on code)
EOF

stile init "$WORK/task.md" --json >/dev/null
echo "ready: cd $WORK"
