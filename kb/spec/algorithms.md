---
id: spec-algorithms
type: spec
summary: Step-by-step algorithm for every stile command, including the save state machine.
domain: spec
last-updated: 2026-05-03
depends-on: [spec-data-model, spec-error-taxonomy]
refines: [prd]
related: [external-diff3, external-posix-fs, properties-functional]
---

# Algorithms

## One-liner
Authoritative step-by-step behaviour for `init`, `open`, `save`, `status`, `resolve`, and `merge3`.

## Scope
Pre/postconditions and ordered steps. JSON output shapes live in `spec/api-contracts.md`. Error names in `spec/error-taxonomy.md`.

## Common preamble (every command)

1. Resolve symlinks: `FILE := os.path.realpath(arg)`.
2. Reject if `FILE` is not a regular file → `UnsupportedFile`.
3. Compute `sidecar := dirname(FILE)/.basename(FILE).stile`.

Mutating commands (`init`, `open`, `save`, `resolve`) THEN:

4. Acquire `flock(LOCK_EX)` on `<sidecar>/lock`. Release on every exit path (success, error, exception). See `external/posix-fs.md#flock`.

## `init`

Pre: `FILE` exists and is a regular file.

```
ensure sidecar dirs exist (mkdir -p sidecar, bases/, conflicts/, tmp/)
acquire lock
current = read(FILE)
reject if not valid utf-8 -> InvalidUtf8
current_sha = H(current)
store_base(current)              # bases/<hex(current_sha)>, deduplicates
if state.json absent or empty:
    write fresh state {format_version=1, target_path=relpath(FILE, sidecar),
                      last_known_sha=current_sha, pending_conflict=null}
else:
    validate format_version == 1 -> else CorruptSidecar
    leave pending_conflict untouched
    update last_known_sha = current_sha
release lock
```

Idempotence: running `init` twice on a clean file MUST succeed and leave a usable sidecar.

## `open`

```
if sidecar missing: run init's body (auto-init)
acquire lock
base = read(FILE)
reject if not valid utf-8 -> InvalidUtf8       (see Note A)
base_sha = H(base)
store_base(base)
state = read state.json
update last_known_sha = base_sha
release lock
return (base_sha, base_path = bases/<hex>, conflicted = state.pending_conflict != null)
```

> **Note A** (deviation from question 20 default): `open` rejects invalid UTF-8 too.
> The auto-init policy means `open` is the typical first call; if `init` enforces UTF-8
> and `open` does not, a caller's first contact with a binary file would silently
> store a base. Better: enforce uniformly. Documented here for traceability.

`base_path` MUST exist on disk and `H(read(base_path)) == base_sha` when `open` returns.

## `save`

Inputs: `FILE`, `--base-sha HASH`, optional `--actor ACTOR`, stdin = `proposed`.

Pre: sidecar exists; `HASH` is syntactically valid (`sha256:` + 64 lowercase hex).

```
acquire lock
state = read state.json (must be format_version=1, else CorruptSidecar)

if state.pending_conflict != null:
    reject ConflictPending

if not exists(bases/<hex(HASH)>):
    reject UnknownBase

base     = read(bases/<hex(HASH)>)
proposed = read(stdin)
reject if proposed not valid utf-8 -> InvalidUtf8
current  = read(FILE)
reject if current not valid utf-8 -> InvalidUtf8

base_sha = HASH
prop_sha = H(proposed)
curr_sha = H(current)

# Branch order matters: noop short-circuits even if base is stale.
if prop_sha == curr_sha:
    store_base(current)
    update last_known_sha = curr_sha
    return saved(mode=noop, sha=curr_sha)

if curr_sha == base_sha:
    atomic_replace(FILE, proposed)
    store_base(proposed)
    update last_known_sha = prop_sha
    return saved(mode=direct, sha=prop_sha)

# stale base AND content differs -> 3-way merge
result = merge3(base, current, proposed)
if result == Clean(merged):
    merged_sha = H(merged)
    atomic_replace(FILE, merged)
    store_base(merged)
    update last_known_sha = merged_sha
    return saved(mode=merged, sha=merged_sha)

if result == Conflict(merged_with_markers):
    id = uuid4_hex()
    create_conflict_dir(id, actor, base, current, proposed, merged_with_markers,
                        base_sha, curr_sha, prop_sha)
    markers_sha = H(merged_with_markers)
    atomic_replace(FILE, merged_with_markers)         # markers visible to user
    store_base(merged_with_markers)
    update state.pending_conflict = {id, base_sha, current_sha=curr_sha,
                                      proposed_sha=prop_sha,
                                      path=conflicts/<id>}
    update state.last_known_sha = markers_sha
    return conflict(id, conflict_path, markers_sha)

if result == ToolError(detail):
    do not modify FILE or sidecar state
    return error MergeToolError (exit 7)

release lock
```

Branch-order rationale (the noop check first): it makes `save` idempotent even when
a stale base is presented but the proposed content already matches disk — avoiding
needless merges that could spuriously conflict.

## `status`

Reading-only; lock optional but recommended for coherent output.

```
if sidecar missing: return unmanaged
acquire lock
state = read state.json (CorruptSidecar if invalid)
current_sha = H(read(FILE))
release lock
if state.pending_conflict: return conflicted(current_sha, pending_conflict)
else: return clean(current_sha, last_known_sha)
```

## `resolve`

Inputs: `FILE`, optional `--actor`. No stdin.

```
acquire lock
state = read state.json
reject if state.pending_conflict is null  -> UsageError ("no pending conflict")
content = read(FILE); reject if not utf-8 -> InvalidUtf8
reject if has_conflict_markers(content)   -> UsageError ("conflict markers present")
sha = H(content)
store_base(content)
state.last_known_sha = sha
state.pending_conflict = null
write state.json
release lock
return resolved(sha)
```

The conflict directory is **kept** on disk for forensics. There is no garbage collection at present.

`has_conflict_markers(content)` returns true iff some line starts with `<<<<<<< ` AND some line starts with `>>>>>>> `. Requiring both rules out false positives from a lone `=======` (Markdown Setext H1 underlines).

## `merge3` (internal)

```
write base, current, proposed to tmp/merge-<rand> files
diff3 -m PROPOSED BASE CURRENT
exit 0  -> Clean(stdout)
exit 1  -> Conflict(stdout)        # stdout has <<<<<<< / ======= / >>>>>>> markers
exit >=2 -> ToolError(stderr)
```

Argument order matches SPEC §8: `proposed` is "MYFILE" (favoured side of markers),
`base` is the common ancestor, `current` is "YOURFILE".

## Atomic replace

```
tmp = tmp/atomic-<rand>
write all bytes to tmp
flush user-space buffers (file.flush())
fsync(tmp)
copymode(FILE, tmp)                # preserve mode bits
try: chown(tmp, FILE.uid, FILE.gid)  except PermissionError: pass
os.replace(tmp, FILE)              # atomic on same fs
fsync(parent_dir(FILE))
```

If any step before `os.replace` raises, `FILE` is untouched. The temp must be on
the same filesystem as `FILE` (we put it inside the sidecar, which is co-located).

## Agent notes
> The save branch order (noop → direct → merge) is load-bearing — see rationale above.
> `merge3` accepting `ToolError` as a third outcome is critical: a missing or broken `diff3` MUST NOT be reported as a content conflict (P10).
> `last_known_sha` is updated on every successful command; it is advisory, never authoritative.

## Related files
- `spec/api-contracts.md` — JSON shapes for every return value
- `spec/error-taxonomy.md` — every reject path's name and exit code
- `external/diff3.md` — runtime behaviour of `diff3 -m`
- `external/posix-fs.md` — flock, fsync, rename semantics
