---
id: index
type: index
summary: Master routing for the cotype KB — start here.
domain: meta
last-updated: 2026-05-03
depends-on: []
refines: []
related: []
---

# cotype — Knowledge Base

## What this KB covers

`cotype` is a tiny CLI that prevents lost updates when a text file is edited
concurrently by a human editor and one or more processes. The core is
deliberately small: `init`, `open`, `save`, `status`, `resolve`, `cat-base`,
with safe atomic writes and 3-way merge via POSIX `diff3`.

## How to use this KB (for agents)

**Before anything else, read:**
1. `GLOSSARY.md` — canonical terms.
2. `architecture/overview.md` — module layout.

**Then navigate by task:** `indexes/by-task.md`.

## Quick-load bundles

| Goal                                  | Load these files (in order)                                                                                                              |
|---------------------------------------|------------------------------------------------------------------------------------------------------------------------------------------|
| Understand what cotype does            | `GLOSSARY.md`, `domain/prd.md`                                                                                                           |
| Implement a command                   | `indexes/by-task.md#implement`, `architecture/overview.md`, `spec/algorithms.md`, `spec/api-contracts.md`, `properties/functional.md`     |
| Implement the merge module            | `architecture/overview.md`, `spec/algorithms.md`, `external/diff3.md`, `architecture/decisions/0002-diff3-for-merge.md`                   |
| Implement atomic_write / lock         | `external/posix-fs.md`, `architecture/decisions/0003-sidecar-flock.md`, `properties/functional.md` (P2, P12, P13)                         |
| Write tests                           | `conventions/testing-strategy.md`, `properties/functional.md`, `properties/edge-cases.md`, `spec/error-taxonomy.md`                       |
| Spec compliance audit                 | `runbooks/audit-checklist.md`, `domain/prd.md`, `spec/INDEX.md`                                                                          |
| Security audit                        | `runbooks/audit-checklist.md`, `conventions/error-handling.md`, `external/diff3.md`                                                      |
| Debug a failing command               | `spec/algorithms.md`, `spec/error-taxonomy.md`, `architecture/overview.md`                                                               |

## Directory map

```
kb/
  GLOSSARY.md                       canonical terms
  INDEX.md                          this file
  domain/prd.md                     product requirements (distilled)
  spec/
    INDEX.md
    data-model.md                   hash, paths, sidecar layout, state.json
    algorithms.md                   per-command behaviour (authoritative)
    api-contracts.md                CLI / JSON shapes
    config-and-formats.md           on-disk schemas
    error-taxonomy.md               named errors + exit codes
    protocols.md                    race-free caller sequences
  properties/
    INDEX.md
    functional.md                   P1..P15 + path-traversal
    non-functional.md               NF1..NF6
    edge-cases.md                   T1..T22 conformance + edge tests
  architecture/
    overview.md                     modules + deps + error hierarchy
    decisions/
      0001-python-stdlib-only.md
      0002-diff3-for-merge.md
      0003-sidecar-flock.md
  external/
    INDEX.md
    diff3.md                        POSIX diff3 -m runtime behaviour
    posix-fs.md                     rename / fsync / flock semantics
  conventions/
    code-style.md
    error-handling.md
    testing-strategy.md
  runbooks/
    audit-checklist.md
  indexes/
    by-task.md                      task-oriented routing
```

## File count & last updated

26 KB files — Last updated: 2026-05-03

## Agent notes
> If a quick-load bundle here disagrees with `indexes/by-task.md`, fix this file — the bundle table is the high-level shortcut; `by-task.md` is the canonical routing.
> When you add a new KB file, add it both to the directory map above AND (if it's a routine task) to `indexes/by-task.md`.

## Related files
- `indexes/by-task.md` — canonical task-oriented routing
- `runbooks/audit-checklist.md` — quality gate
