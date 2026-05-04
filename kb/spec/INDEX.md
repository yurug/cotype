---
id: spec-index
type: index
summary: Routing table for the normative spec — pick the file matching your question.
domain: spec
last-updated: 2026-05-03
depends-on: []
refines: []
related: [index]
---

# Spec — Index

## One-liner
Routing for the normative spec. Open the file whose summary answers your question.

## Files

- `data-model.md` — hash format, paths, sidecar layout, state.json shape.
- `algorithms.md` — step-by-step for `init`, `open`, `save`, `status`, `resolve`, `merge3`, `atomic_replace`. Single source of truth for behaviour.
- `api-contracts.md` — CLI flags, JSON success/conflict envelopes per command.
- `config-and-formats.md` — schemas for state.json, conflict meta.json, base/conflict file conventions.
- `error-taxonomy.md` — every stable error name + when it fires + exit code.
- `protocols.md` — race-free caller sequences (editor, process, and the forbidden pattern that loses updates).

## Reading order for first-time implementers

1. `data-model.md` — establishes vocabulary
2. `algorithms.md` — establishes behaviour
3. `error-taxonomy.md` — establishes failure surface
4. `api-contracts.md` — establishes the integration shape
5. `protocols.md` — establishes how a correct caller drives the API
6. `config-and-formats.md` — establishes on-disk persistence

## Agent notes
> If two spec files appear to disagree, `algorithms.md` wins on behaviour and `data-model.md` wins on shape. Update the loser to match.

## Related files
- `../GLOSSARY.md` — terms used here
- `../properties/INDEX.md` — invariants implied by these specs
