---
id: prd
type: spec
summary: Product requirements distilled — what stile is, who uses it, what it must and must not do in v0.
domain: product
last-updated: 2026-05-02
depends-on: [glossary]
refines: []
related: [spec-algorithms, properties-functional]
---

# Product Requirements — stile v0

## One-liner
A small CLI that prevents lost updates when a text file is edited concurrently by a human and one or more processes.

## Scope
Distilled from `/PRD.md`. Authoritative product intent. For normative behaviour see `spec/`.

## Product principle (verbatim)

> No actor writes the target file directly during managed operation.
> Actors submit candidate file contents to stile.
> stile either writes atomically, merges safely, or rejects with a conflict.

## What stile does
- `init` — creates sidecar, captures the current file as the first base.
- `open` — captures a fresh base snapshot and returns `(base_sha, base_path)` so the caller can load the exact bytes it will later submit `save` against.
- `save` — replaces FILE with the proposed bytes if safe (`direct`), merges if compatible (`merged`), short-circuits if equal (`noop`), or refuses with a conflict.
- `status` — reports current hash, last-known hash, pending conflict (if any), or "unmanaged".
- `resolve` — clears a pending conflict by accepting a tool/human-provided resolved version.

## What stile does NOT do (v0)
- network sync, multi-user real-time collab, CRDTs
- event sourcing / append-only logs
- semantic edits (JSON-path, YAML, AST)
- multi-file transactions
- VCS history
- binary file support
- daemon mode / watch mode
- editor plugins (out of repo scope)

## Users
1. **Human editor** — uses `open` on file load, `save` on write.
2. **Process writer** — formatters, generators, scripts that use `open` then `save` like an editor.
3. **Tool author** — writes editor plugins; needs precise return codes and JSON output.

## Core user stories
- US1: Direct save when no one else changed the file → `direct`.
- US2: Auto-merge when another actor changed disjoint lines → `merged`.
- US3: Conflict instead of lost update → `conflict`, FILE unchanged.
- US4: Same protocol for humans and processes (no privileged writers).

## Required v0 commands
`init | open | save | status | resolve`

## Optional v0 commands (nice-to-have)
`cat-base | clean | version`

## Success looks like
"Boring, predictable, small." If a user can describe the behaviour in two sentences and predict the outcome of any sequence of calls, we won.

## Agent notes
> Every behaviour in this file is REFINED by `spec/` files; defer to spec on disagreements.
> The "do NOT" list is load-bearing — refuse scope creep that pushes any of those items into v0.

## Related files
- `spec/algorithms.md` — exact `save` semantics
- `spec/data-model.md` — sidecar layout, hash, paths
- `properties/functional.md` — invariants implied by the user stories
