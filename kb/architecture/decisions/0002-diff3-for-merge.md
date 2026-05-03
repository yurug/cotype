---
id: adr-0002
type: decision
summary: ADR-0002 — implement merge3 by invoking POSIX `diff3 -m` in subprocess, not by hand-rolling.
domain: architecture
last-updated: 2026-05-02
depends-on: [adr-0001]
refines: []
related: [architecture-overview, external-diff3, properties-functional]
---

# ADR-0002: Use POSIX `diff3 -m` for 3-way merge

## Context

SPEC §8 explicitly permits a deterministic internal 3-way line merge OR `diff3`. We need a merge that:
- Is correct on disjoint line edits (Clean) and conflicts on overlapping edits (Conflict).
- Is deterministic across hosts.
- Has well-understood conflict-marker output.

Writing a 3-way line merger from scratch is roughly 200 lines of code that must be exhaustively tested against pathological cases (overlapping deletions, identical insertions on both sides, trailing-newline edge cases). Every bug is a correctness regression.

`diff3` is decades-old, ships in `diffutils`, and is on every POSIX-ish host. Its `-m` mode emits the merged file with `<<<<<<< ... ||||||| ... ======= ... >>>>>>>` markers when ranges overlap.

## Decision

`merge.py` invokes `diff3 -m PROPOSED BASE CURRENT` via `subprocess.run([...])` (list form, never shell). It interprets:

- Exit 0: Clean merge — stdout is the merged content.
- Exit 1: Content conflict — stdout has conflict markers; we treat this as the v0 conflict result.
- Exit ≥2: Tool error (missing, internal failure) — surface as `MergeToolError` (P10).

If `diff3` is missing on `PATH`, we raise `MergeToolError` immediately (no fallback).

## Consequences

Positive:
- ~30 lines of glue instead of 200 lines of merge.
- Defers correctness to a battle-tested external tool.
- Conflict markers are the format users already recognise from Git.

Negative:
- Adds a runtime dependency (`diffutils`). Documented in README.
- Subprocess overhead per merge (~5–20 ms). Negligible for editor-paced use.
- No fine control over conflict-marker style or merge heuristics (acceptable — KISS).

Rejected alternatives:
- **Internal Python merge** (e.g. via `difflib.ndiff` + custom 3-way logic). Doable, but ships correctness risk we don't need.
- **Vendor a Python diff3 implementation**. Adds a third-party dep, contradicts ADR-0001.

## What this means for implementers

- Argument order is **PROPOSED, BASE, CURRENT** (mine, ancestor, theirs). See `external/diff3.md`.
- Use `tempfile.NamedTemporaryFile` inside `<sidecar>/tmp/` for the three input files. Same filesystem matters less here than for atomic_replace, but co-locating keeps cleanup simple.
- Capture both stdout AND stderr. Treat stdout as the merged content; stderr as the diagnostic for tool errors.
- Never invoke `diff3` via `shell=True` or via `os.system`. P-path-traversal-safety / T19.

## Reconsider when

We need merge semantics POSIX `diff3` cannot express (e.g. semantic merge of structured data). That's a v1 concern.

## Related files
- `../overview.md`
- `../../external/diff3.md` — runtime behaviour
- `../../properties/functional.md` — P10
