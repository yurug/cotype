---
id: runbook-audit-checklist
type: procedure
summary: Multi-axis quality audit checklist — security, performance, UX, spec compliance.
domain: runbook
last-updated: 2026-05-03
depends-on: [properties-functional, spec-error-taxonomy]
refines: []
related: [conventions-testing-strategy]
---

# Audit checklist

## One-liner
Run through this list before each release. Treat any unchecked critical/high as a blocker.

## Section A — Spec compliance

- [ ] Every command in PRD §12 (init, open, save, status, resolve) is implemented and tested.
- [ ] JSON output shapes in `spec/api-contracts.md` match real CLI output byte-for-byte (key order may vary; structure must match).
- [ ] Every error name in `spec/error-taxonomy.md` is reachable by at least one input.
- [ ] Exit codes match the table.
- [ ] `state.json` written by cotype validates against `spec/config-and-formats.md`.
- [ ] Sidecar layout matches `spec/data-model.md`.

## Section B — Properties

- [ ] P1 (no silent stale overwrite) — covered by T6 test.
- [ ] P2 (atomic visibility) — covered by T10 test.
- [ ] P3 (sidecar auxiliary) — manual: rm sidecar, FILE intact.
- [ ] P4 (conflicts explicit) — covered by T6 test (asserts all 4 sub-conditions).
- [ ] P5 (hash byte-exact) — random-bytes test.
- [ ] P6 (lock held during mutation) — concurrent-save test (T21).
- [ ] P7 (pending blocks save) — T7 test.
- [ ] P8 (unknown base rejected) — T9 test.
- [ ] P9 (protocol parity) — same-test-suite-with-different-actor pass.
- [ ] P10 (tool error != content conflict) — T20 test (PATH stripped of diff3).
- [ ] P11 (init idempotent) — T1 test.
- [ ] P12 (atomic replace) — T10 test + code review of `atomic_write.py`.
- [ ] P13 (mode preserved) — explicit test creating 0640 file.
- [ ] P14 (noop short-circuit) — T4 test.
- [ ] P15 (base_path matches base_sha) — T2 test.
- [ ] P-path-traversal-safety — T22 (sidecar paths only built from server-side hex/uuid).

## Section C — Security

- [ ] No `subprocess.run(..., shell=True)`. Grep the codebase.
- [ ] No `os.system`, no `eval`, no `exec`.
- [ ] All paths inside the sidecar are derived from a fixed scheme; no user string concatenated into a path without validation.
- [ ] Sidecar conflict ids are server-generated (uuid4 hex from `save`), never accepted from a CLI flag.
- [ ] `--actor` is stored verbatim in `meta.json`; never used to build a path.
- [ ] Temp file creation uses `tempfile.NamedTemporaryFile` or `mkstemp` — never predictable names.
- [ ] No secrets in error messages or logs.

## Section D — Performance & resource

- [ ] NF1: `save` of 1 MB file p95 <100 ms (manual measure).
- [ ] NF2: 100-line merge <250 ms.
- [ ] NF3: 100 MB save peaks at <3× file size in memory.
- [ ] NF6: `cotype --help` <120 ms cold.
- [ ] No accidental O(N²) — diff/merge is O(N) line-based per `diff3`.

## Section E — UX

- [ ] `--help` is informative; lists every subcommand.
- [ ] Error messages name the file, the relevant hash, and the next step the user can take.
- [ ] Without `--json`, output is one human line; with `--json`, output is a single JSON object on stdout.
- [ ] Exit codes match the documented table; no surprise codes.
- [ ] Tab-completable subcommand names (no aliases that shadow each other).

## Section F — Robustness

- [ ] Crash mid-write: temp file remains in `tmp/`; FILE intact; next command can proceed (may clean stragglers).
- [ ] Crash mid-state.json write: state.json was written via atomic-replace, so either old or new is on disk.
- [ ] flock released on every error path (verify via `pytest -k 'lock and error'`).
- [ ] Corrupt state.json detected and rejected with `CorruptSidecar`.
- [ ] Orphan conflict directory (no state reference) — `status` SHOULD warn (optional, currently deferred).

## Section G — Simplicity

- [ ] Could any module be deleted? (Often yes after first audit.)
- [ ] Could any function be inlined or split? (Apply <30-line rule.)
- [ ] Any abstractions speculative? (No "for future extension" indirection.)
- [ ] Any `try/except` swallowers? (None permitted.)

## Section H — KB & docs

- [ ] README documents install + 5 commands + diff3 prerequisite.
- [ ] All KB cross-refs resolve.
- [ ] No stale `last-updated` dates on files modified this slice.

## How to use

Run section-by-section before each release. Record findings (e.g. via PR description, issue, or a local report file). Fix all critical and high; document residual mediums with rationale.

## Agent notes
> Don't mass-tick boxes; for each, name the test or commit that proves it.
> If you can't tick a box, raise it as an issue — do NOT silently leave it unchecked.

## Related files
- `../properties/functional.md`
- `../spec/error-taxonomy.md`
- `../conventions/testing-strategy.md`
