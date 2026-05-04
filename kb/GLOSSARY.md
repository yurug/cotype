---
id: glossary
type: glossary
summary: Canonical names for every domain term used across the cotype KB.
domain: meta
last-updated: 2026-05-03
depends-on: []
refines: []
related: [index, prd, spec-data-model]
---

# Glossary

## One-liner
Canonical definitions for every domain term used across the KB. Load this first.

## Scope
Terms that appear in more than one KB file. File-local terms are defined inline.

## Terms

- **target file (FILE)**: the regular UTF-8 text file under management. The thing readers read. Always a real path (symlinks resolved).
- **sidecar**: the directory `dirname(FILE)/.basename(FILE).cotype` holding cotype's auxiliary state (lock, state.json, bases, conflicts, tmp). See `spec/data-model.md`.
- **base / base snapshot**: the bytes the caller observed at the start of an edit, captured by `open` and stored content-addressed in `bases/<hex>`. The common ancestor of a 3-way merge.
- **current**: the bytes presently on disk in the target file. Re-read every time a command needs them — never trusted from `last_known_sha`.
- **proposed**: the bytes the caller wants written, supplied via stdin to `save` or `resolve`.
- **merged**: the result of `merge3(base, current, proposed)` when the merge is clean.
- **3-way merge / `merge3`**: the function `(base, current, proposed) -> Clean(bytes) | Conflict(data)`. Implemented as POSIX `diff3 -m`. See `spec/algorithms.md` and `external/diff3.md`.
- **hash / sha**: `"sha256:" ++ lowercase_hex(SHA256(bytes))`. Byte-exact, no normalisation. See `spec/data-model.md`.
- **base_sha**: the hash of a base snapshot. Identifies which `bases/<hex>` file the caller is referring to.
- **base_path**: the path to a base snapshot file. The race-free way for an editor or process to load the bytes the snapshot represents.
- **actor**: opaque label identifying the caller (e.g. `emacs`, `my-formatter`, `unknown`). Recorded in conflict `meta.json`. Does not affect semantics.
- **pending conflict**: an unresolved 3-way conflict. Blocks ordinary `save` until cleared by `resolve`. State lives in `state.json` and `conflicts/<id>/`.
- **conflict id**: opaque identifier for a pending conflict. UUID v4 hex (no dashes).
- **atomic replace**: the rename-based protocol that swaps `FILE` with new bytes in one filesystem-visible step (tmp -> fsync -> rename -> fsync parent). See `spec/algorithms.md` and `external/posix-fs.md`.
- **advisory lock**: an `fcntl.flock(LOCK_EX)` on `.cotype/lock`. Cooperatively serialises mutating commands. Does not prevent direct writes by ill-behaved actors.
- **mode (save mode)**: one of `direct`, `merged`, `noop` — see `spec/algorithms.md#save`.
- **stable error name**: one of the strings in `spec/error-taxonomy.md`. Appears verbatim in the JSON `error` field; never localised.
- **exit code**: integer per SPEC §9 — `0 success | 1 conflict | 2 usage | 3 unmanaged/corrupt | 4 unknown base | 5 pending conflict | 6 io | 7 merge tool`.

## Agent notes
> Load this file early; misreading a term silently produces wrong code.
> If you find a term used inconsistently anywhere in the KB or code, fix it here first, then propagate.

## Related files
- `INDEX.md` — master routing
- `spec/data-model.md` — formal definitions of hash, paths, sidecar layout
- `spec/algorithms.md` — where save modes are determined
