---
id: properties-functional
type: constraint
summary: P1..P15 — functional invariants cotype must always uphold, with violation examples.
domain: properties
last-updated: 2026-05-03
depends-on: [spec-algorithms, spec-data-model]
refines: []
related: [properties-edge-cases, properties-non-functional]
---

# Functional properties (invariants)

## One-liner
The invariants that, if any one is violated, the tool is incorrect by definition.

## Scope
Functional only. Performance and resource limits are in `non-functional.md`. Specific edge cases that exercise these are in `edge-cases.md`.

## Format

Each property has: **ID**, **statement**, **violation example**, **why**, **test strategy**.

---

### P1 — No silent stale overwrite

**Statement.** If `H(read(FILE)) != base_sha`, then `save` must NOT replace `FILE` with `proposed`. It must either produce a clean merge or report a conflict.

**Violation.** A user opens `A`, the file becomes `B` on disk, the user submits `C` overlapping `B`, and cotype writes `C`. `B` is lost.

**Why.** Core PRD invariant I1; the entire reason this tool exists.

**Test.** T6 (stale conflicting save) — assert FILE bytes equal `current` after the save.

---

### P2 — Atomic visibility

**Statement.** A concurrent reader of `FILE` observes either the pre-write bytes or the post-write bytes. Never a prefix, suffix, mix, or empty file.

**Violation.** Reader sees zero-length FILE, or first half of new and second half of old.

**Why.** I2; readers (build systems, watchers) cannot distinguish "torn write" from "real new state".

**Test.** T10 — reader thread hashes FILE in a loop while writer alternates large contents; every observed hash MUST be in the set of fully-written versions.

---

### P3 — Sidecar snapshots are auxiliary

**Statement.** `FILE` is a normal file. `bases/` enables 3-way merge but is not authoritative content. Deleting the sidecar must not corrupt `FILE`.

**Violation.** Implementation reads `FILE` content from `bases/` instead of `FILE` itself.

**Why.** I3; preserves "boring file" semantics for non-cotype readers.

**Test.** Manual: rm sidecar; FILE still readable, contents unchanged.

---

### P4 — Conflicts are explicit

**Statement.** On `save` returning `conflict`, (a) FILE byte-for-byte equals the diff3 marker output (i.e. contains a `<<<<<<< ` opener AND a `>>>>>>> ` closer line), (b) `state.pending_conflict != null` and `state.last_known_sha == H(FILE)`, (c) `conflicts/<id>/{base,current,proposed,merged,meta.json}` all exist with their respective bytes, (d) exit code is 1.

**Violation.** Conflict reported but FILE has neither markers nor was rolled back to `current`; missing forensic artifacts; `last_known_sha` desynced from FILE.

**Why.** I4; the user must see the conflict in their own editor (git-style) so they can resolve it inline, while downstream tooling still has a deterministic forensics trail in the sidecar.

**Test.** T6 — assert all four sub-conditions.

---

### P5 — Hash is byte-exact

**Statement.** `H(b)` operates on the literal bytes from `read(FILE)`. No normalisation: line endings preserved, BOMs preserved, trailing newline preserved or absent as written.

**Violation.** `H` strips a trailing `\n` and now `bases/<hex>` doesn't match the bytes that produced it.

**Why.** Spec §2.1; any normalisation would silently desynchronise the actor's view from disk.

**Test.** Hash a file with `\r\n`, no trailing newline, BOM — round-trip via `bases/<hex>` and assert byte-equality.

---

### P6 — Mutating commands hold the sidecar lock

**Statement.** `init`, `open`, `save`, `resolve` acquire `flock(LOCK_EX)` on `<sidecar>/lock` for the duration of their state mutation.

**Violation.** Two concurrent `save`s observe the same `pending_conflict == null`, both try to `atomic_replace`, last-writer-wins.

**Why.** Without the lock, the race-free contracts in SPEC §11 don't hold.

**Test.** Run two `save`s in parallel against the same FILE with conflicting bases; exactly one succeeds, the other sees the result of the first (becomes a stale-base case).

---

### P7 — Pending conflict blocks ordinary save

**Statement.** While `state.pending_conflict != null`, `save` returns `ConflictPending`, exit 5, FILE unchanged by the rejected save (the markers from the conflicting save remain).

**Violation.** Saving over a pending conflict silently overwrites the markers and loses one side of the conflict.

**Why.** Forces explicit resolution via `cotype resolve` after the user has edited out the markers; preserves both sides until then.

**Test.** T7 — after T6, attempt `save`; assert exit 5 and FILE bytes unchanged.

---

### P8 — Unknown base rejection

**Statement.** `save --base-sha HASH` where no `bases/<hex(HASH)>` exists returns `UnknownBase`, exit 4, FILE and state unchanged.

**Violation.** Implementation accepts and treats it as if base equalled current.

**Why.** Otherwise a malicious or broken caller can fabricate a base and force overwrites.

**Test.** T9.

---

### P9 — Protocol parity (humans == processes)

**Statement.** A process using only `open`/`save`/`resolve` gets the same correctness guarantees as an editor. There is no privileged code path.

**Violation.** A `--actor` value triggers different behaviour somewhere (e.g. relaxes lock).

**Why.** US4; PRD §10.

**Test.** Run all conformance tests with `--actor human`, then again with `--actor process`. Outcomes identical.

---

### P10 — Merge tool error is not a content conflict

**Statement.** If `merge3` cannot run (`diff3` missing) or returns a non-content error (exit ≥2), the result is `MergeToolError` (exit 7). FILE and `state.pending_conflict` are unchanged.

**Violation.** A missing `diff3` is reported as `conflict` (exit 1) and a phony conflict directory is created.

**Why.** Otherwise a sysadmin issue silently denies legitimate saves and pollutes the conflict log.

**Test.** Stub `PATH` to drop `diff3`; trigger a stale-base save; assert exit 7, no conflict dir created.

---

### P11 — `init` is idempotent

**Statement.** Running `init` twice on a clean, managed file succeeds both times. Sidecar contents (other than possibly `last_known_sha`) are equivalent.

**Violation.** Second `init` deletes the sidecar or breaks an existing pending conflict.

**Why.** Editors and scripts may speculatively call `init`; any non-idempotent behaviour creates flakiness.

**Test.** T1.

---

### P12 — Atomic replace via tmp-and-rename on the same filesystem

**Statement.** `atomic_replace(FILE, b)` writes a temp file under `<sidecar>/tmp/`, fsyncs it, then `os.replace`s it over `FILE`, then fsyncs the parent directory.

**Violation.** Direct `open(FILE, 'wb')` write — torn writes possible.

**Why.** Same-fs rename is the only POSIX atomic file-swap primitive. fsyncs guarantee crash-resilience of the new contents and the directory entry.

**Test.** Reviewer reads `atomic_write.py`; T10 catches gross violations.

---

### P13 — Permissions preserved on replacement

**Statement.** After `atomic_replace`, FILE's mode bits equal what they were before. Owner/group preserved when the running user has permission.

**Violation.** A file that was `0640` becomes `0644` after `save`.

**Why.** Some files are intentionally restricted; we mustn't broaden access.

**Test.** Create FILE `0640`; run `save`; assert mode still `0640`.

---

### P14 — Noop short-circuits before merge

**Statement.** If `H(proposed) == H(current)`, `save` returns `noop` even when `base_sha != H(current)`. No merge attempt is made; FILE is not rewritten.

**Violation.** Implementation merges or rewrites FILE when proposed already matches current. Spurious churn or false conflict.

**Why.** Idempotence under retries; avoids gratuitous diff3 invocations.

**Test.** T4.

---

### P15 — `open` returns a base_path that hashes to base_sha

**Statement.** When `open` returns `(base_sha, base_path)`, then `H(read(base_path)) == base_sha` and `base_path` exists. This holds at least until the next mutating command on this sidecar (no garbage collection at present, so effectively forever).

**Violation.** `base_path` is wrong, missing, or stores different bytes (e.g. `bases/<hex>` was overwritten).

**Why.** The race-free editor protocol depends on the editor reading `base_path`, not `FILE` again.

**Test.** T2.

---

### P-path-traversal-safety (no ID; cross-cutting)

**Statement.** All paths inside the sidecar are derived from a fixed scheme rooted at the sidecar dir. No user-supplied string (actor, base-sha hex, etc.) is concatenated into a filesystem path without validation. Conflict ids are generated server-side (uuid4 hex) and never accepted from the user.

**Violation.** A future CLI flag accepts a caller-supplied id and concatenates it into a sidecar path without validation, allowing escape.

**Why.** Defence in depth: even if an attacker controls a CLI flag, they can't escape the sidecar.

**Test.** Path components built from caller input go through hex/regex validators (see `paths.py`).

## Agent notes
> Every test for a property should reference its ID in its name (e.g. `test_P1_no_silent_overwrite`).
> When the spec evolves, update properties FIRST, then code, then tests.

## Related files
- `edge-cases.md` — boundary scenarios that exercise these properties
- `non-functional.md` — performance/resource invariants
- `../runbooks/audit-checklist.md` — multi-axis review using these IDs
