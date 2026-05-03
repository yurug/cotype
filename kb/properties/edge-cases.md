---
id: properties-edge-cases
type: constraint
summary: T1..T20 — boundary conditions and conformance tests with expected behaviour.
domain: properties
last-updated: 2026-05-03
depends-on: [spec-algorithms, properties-functional]
refines: []
related: []
---

# Edge cases & conformance tests

## One-liner
Concrete boundary scenarios. T1..T10 are SPEC §14 conformance tests; T11+ are additional edges we discovered.

## Format

Each entry: **ID** · **scenario** · **expected** · **enforces**.

---

### T1 — init idempotence
- Scenario: `init FILE` twice on a clean file.
- Expected: both succeed; sidecar preserved; second call does not erase or perturb a hypothetical pending conflict.
- Enforces: P11.

### T2 — open stores exact base
- Scenario: `open FILE`; read returned `base_path`.
- Expected: `H(read(base_path)) == base_sha`.
- Enforces: P15, P5.

### T3 — direct save
- Scenario: file `A`, base `A`, proposed `B`.
- Expected: `mode=direct`, FILE bytes = `B`, `last_known_sha = H(B)`.
- Enforces: P1 (negative direction), P12.

### T4 — noop save
- Scenario: file `B`, base `A`, proposed `B`.
- Expected: `mode=noop`, FILE bytes still `B`, no merge attempted, no conflict.
- Enforces: P14.

### T5 — stale compatible save (auto-merge)
- Scenario (truly disjoint per `external/diff3.md#Adjacency`):
  `base = "a\nb\nc\nd\ne\n"`, `current = "a\nB\nc\nd\ne\n"` (line 2 edited),
  `proposed = "a\nb\nc\nd\nE\n"` (line 5 edited).
- Expected: `mode=merged`, FILE bytes contain both `B` and `E`, no conflict.
- Enforces: P1, merge3 cleanliness.
- Note: SPEC §14's three-line example is illustrative only — `diff3` groups
  adjacent line edits into one region and reports a conflict for it. SPEC §8
  says Clean is `SHOULD` (not `MUST`) for non-overlapping edits, so this is
  conformant.

### T6 — stale conflicting save
- Scenario: `base = "x\ny\nz\n"`, `current = "x\ny-current\nz\n"`, `proposed = "x\ny-proposed\nz\n"`.
- Expected: `status=conflict` exit 1, FILE bytes = `current`, `conflicts/<id>/{base,current,proposed,meta.json}` all written, `state.pending_conflict.id == id`.
- Enforces: P1, P4.

### T7 — pending conflict blocks save
- Scenario: after T6, attempt any `save`.
- Expected: `error=ConflictPending`, exit 5, FILE unchanged.
- Enforces: P7.

### T8 — resolve clears conflict
- Scenario: after T6, run `resolve --conflict-id <id> < resolved-bytes`.
- Expected: exit 0, FILE bytes = resolved, `state.pending_conflict == null`, `status` reports `clean`.
- Enforces: P4 (post-resolution cleanup), P12.

### T9 — unknown base
- Scenario: `save --base-sha sha256:<valid syntax but no bases/<hex>>`.
- Expected: `error=UnknownBase`, exit 4, FILE unchanged.
- Enforces: P8.

### T10 — atomicity smoke test
- Scenario: writer thread does `save` repeatedly with two distinct large contents `V1`, `V2` (~5 MB each, base updated each round); reader thread reads FILE in a loop and hashes.
- Expected: every observed hash ∈ `{H(V1), H(V2)}`. Never a third hash, never an empty read, never a partial read.
- Duration: 2 seconds or 200 iterations, whichever is shorter.
- Enforces: P2, P12.

---

### T11 — empty FILE
- Scenario: FILE is zero bytes; `init`/`open`/`save` flows.
- Expected: hash is `H(b"")` = `sha256:e3b0c44...`. Everything works.

### T12 — file without trailing newline
- Scenario: FILE = `"abc"` (no `\n`).
- Expected: hash matches; `direct` save preserves bytes; `merge3` (if reached) does not insert a newline silently.
- Enforces: P5.

### T13 — CRLF / mixed line endings
- Scenario: FILE has `\r\n` lines.
- Expected: hash byte-exact. `diff3 -m` may produce slightly different markers but does not normalise — we treat its output as bytes.
- Enforces: P5.

### T14 — large file (10+ MB)
- Scenario: 50 MB plain-ASCII FILE.
- Expected: `init`/`save` work; memory stays bounded (NF3); no obvious slowness blockers.

### T15 — corrupt state.json
- Scenario: hand-edit `state.json` to invalid JSON or set `format_version: 2`.
- Expected: every mutating command rejects with `CorruptSidecar`, exit 3.
- Enforces: P-path-traversal-safety (defensively), failure containment.

### T16 — base referenced but file missing
- Scenario: `state.last_known_sha = sha256:X`, but `bases/X` deleted.
- Expected: `save --base-sha sha256:X` returns `UnknownBase`. `status` still works.

### T17 — symlink target
- Scenario: FILE is a symlink to `real-file.txt`.
- Expected: `realpath` resolves; sidecar attaches to `real-file.txt`. `init` on the symlink and on the real file produce the same sidecar.

### T18 — relative vs absolute FILE arg
- Scenario: `stile init ./notes/todo.txt` then `stile open /home/me/notes/todo.txt`.
- Expected: same sidecar found; same operations.

### T19 — actor with shell metacharacters
- Scenario: `--actor 'rm -rf $HOME'`.
- Expected: stored verbatim in `meta.json`. NEVER passed through a shell; merge tool invocation uses `subprocess.run([...])` (list form).
- Enforces: security — see `runbooks/audit-checklist.md`.

### T20 — diff3 missing
- Scenario: `PATH` does not contain `diff3`, run a stale-base save.
- Expected: `error=MergeToolError`, exit 7. No conflict directory created. FILE unchanged.
- Enforces: P10.

### T21 — concurrent `open` then concurrent `save` race
- Scenario: two processes call `open` (each gets its own base_sha — possibly identical), then both call `save` with disjoint changes.
- Expected: one wins as `direct` or `merged`; the other observes that (now stale) and either merges or conflicts. Never both succeed silently.
- Enforces: P6, P1.

### T22 — `--conflict-id ../escape`
- Scenario: malicious resolve attempt.
- Expected: validation rejects (must be 32 lowercase hex chars). `UsageError` exit 2.
- Enforces: P-path-traversal-safety.

## Agent notes
> Test names should embed both the property ID (`P_`) and the edge-case ID (`T_`) when relevant: `test_T6_P4_stale_conflicting_save`.
> Edge cases that grow over time should be appended here, not folded into functional.md — keep concerns separate.

## Related files
- `functional.md` — properties referenced above
- `non-functional.md` — quantitative bounds
