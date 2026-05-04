---
id: properties-non-functional
type: constraint
summary: NF1..NF6 — non-functional measurable criteria (perf, resource use, portability).
domain: properties
last-updated: 2026-05-03
depends-on: [properties-functional]
refines: []
related: [properties-edge-cases]
---

# Non-functional properties

## One-liner
Performance, resource, and portability targets. Loose bounds — `stile` is correctness-first.

---

### NF1 — Steady-state save under load

**Statement.** A `save` of a 1 MB file with a clean direct path completes in <100 ms wall-time on a modern Linux laptop (warm cache, local SSD).

**Why.** Editor saves should feel instant.

**Measure.** `time stile save FILE --base-sha ... < 1MB-file`. Repeat 10×, assert p95 <100 ms.

---

### NF2 — Merge under typical load

**Statement.** A 3-way merge of three 100-line files via `diff3 -m` completes in <250 ms wall-time.

**Why.** Real-world editor saves on real-world files.

**Measure.** Smoke-tested in CI; not asserted strictly.

---

### NF3 — Memory bound

**Statement.** Peak resident memory is O(file size). A 100 MB FILE save MUST NOT load multiple copies (we read once into bytes; tolerate ~3× while merging).

**Why.** Sanity bound; `stile` does not promise streaming.

**Measure.** Manual check on a 100 MB synthetic file.

---

### NF4 — Disk usage

**Statement.** Each unique base content costs `len(content)` bytes plus a few hundred bytes of metadata. There is no garbage collection at present.

**Why.** Honesty: bases accumulate. Optional `clean` command may garbage-collect later.

**Measure.** Inspect `bases/` after a session of N opens.

---

### NF5 — Portability

**Statement.** Runs on Linux and macOS with Python ≥3.11 and POSIX `diff3`. No Windows support (pathing, flock semantics differ).

**Why.** Scope limit; KISS.

**Measure.** CI matrix Linux + macOS.

---

### NF6 — Startup overhead

**Statement.** Cold `stile --help` returns in <120 ms. Imports kept lean (no heavy dynamic loads).

**Why.** Editor integrations call stile per save; startup should not feel like a stall.

**Measure.** `time stile --help` on a warm Python install.

## Agent notes
> These are loose targets. Failing a number is a signal to investigate, not an automatic blocker.
> If a future feature blows NF6, factor the slow imports into a lazy submodule.

## Related files
- `functional.md` — invariants (the hard ones)
- `edge-cases.md` — scenarios that exercise large/edge inputs
