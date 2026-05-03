---
id: properties-index
type: index
summary: Routing for invariants — pick by category.
domain: properties
last-updated: 2026-05-03
depends-on: []
refines: []
related: [index]
---

# Properties — Index

## One-liner
Where to look for invariants, quantitative bounds, and concrete test scenarios.

## Files

- `functional.md` — P1..P15 + path-traversal property. The hard "must always be true" set.
- `non-functional.md` — NF1..NF6. Performance, memory, portability, startup overhead.
- `edge-cases.md` — T1..T22. SPEC §14 conformance tests + extra edges.

## Quick map

| If you're asking...                                | Read                  |
|----------------------------------------------------|-----------------------|
| What invariants must my code uphold?               | `functional.md`       |
| What's the perf target for save?                   | `non-functional.md`   |
| What inputs must I test against?                   | `edge-cases.md`       |
| Which property does test T6 enforce?               | `edge-cases.md` then  |
|                                                    | trace to `functional.md` |

## Agent notes
> When you change a property, update edge-cases that reference it on the same commit. Stale references silently weaken tests.

## Related files
- `../runbooks/audit-checklist.md`
- `../spec/INDEX.md`
