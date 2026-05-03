---
id: by-task
type: index
summary: Given a task type (implement, audit, debug, test), the ordered list of KB files to load.
domain: meta
last-updated: 2026-05-02
depends-on: []
refines: []
related: [index]
---

# Task-oriented routing

## One-liner
Pick the section matching what you're about to do; load the listed files in order.

---

## `implement`

### A new module / command
1. `architecture/overview.md` — module dependencies; where the new code goes.
2. `spec/algorithms.md` — exact behaviour you must reproduce.
3. `spec/api-contracts.md` — JSON shapes (if touching CLI surface).
4. `spec/error-taxonomy.md` — which named errors this code path can raise.
5. `properties/functional.md` — invariants this code must enforce; cite IDs in tests.
6. `external/INDEX.md` — open the SDK file if your module touches `diff3` or POSIX FS primitives.
7. `conventions/code-style.md` — style/size limits.
8. `conventions/error-handling.md` — raising and translating errors.

**Key questions answered:** What inputs/outputs? What invariants? What error names?

### A new test
1. `conventions/testing-strategy.md`
2. `properties/functional.md` & `properties/edge-cases.md` — IDs to use in test name.
3. `spec/error-taxonomy.md` — for error-path tests.

---

## `audit`

### Security audit
1. `runbooks/audit-checklist.md` — sections C, F.
2. `external/INDEX.md` + `external/diff3.md` — subprocess invocation surface.
3. `conventions/error-handling.md` — leakage in messages.

### Spec compliance audit
1. `runbooks/audit-checklist.md` — section A.
2. `domain/prd.md`
3. `spec/INDEX.md` (then walk the listed files).

### Property compliance audit
1. `runbooks/audit-checklist.md` — section B.
2. `properties/functional.md` (then `edge-cases.md` for tests).

---

## `debug`

### A failing command
1. `spec/algorithms.md` — what should happen, step by step.
2. `spec/error-taxonomy.md` — to understand what error name surfaced.
3. `architecture/overview.md` — which module owns this.
4. The relevant `external/*.md` if subprocess or filesystem behaviour is suspect.

### A property violation
1. `properties/functional.md` — find the property by ID.
2. The property's referenced test in `properties/edge-cases.md`.
3. The module enforcing it (per `architecture/overview.md` — error hierarchy + dependency graph).

---

## `test`

1. `conventions/testing-strategy.md`
2. `properties/functional.md` — invariants list (use IDs in test names).
3. `properties/edge-cases.md` — TIDs.
4. `spec/error-taxonomy.md` — error paths to assert.

---

## Agent notes
> When a new task class appears (e.g. "release", "doc-update"), add a section here. The bare directory listing in INDEX.md is not enough.
> Indexes are routing tables, not summaries. Keep entries to one line; if you need detail, link to the file.

## Related files
- `../INDEX.md` — quick-load bundles
- `../runbooks/audit-checklist.md`
