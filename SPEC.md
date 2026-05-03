# SPEC: stile v0

## 1. Status

This document is the normative v0 specification for `stile`, a local safe-save tool for concurrently edited text files.

The terms MUST, SHOULD, MAY, and MUST NOT are normative.

## 2. Definitions

### 2.1 Text

v0 supports regular UTF-8 text files.

The implementation MUST hash raw bytes exactly as read from disk. It MUST NOT normalize line endings, Unicode, whitespace, or final newlines before hashing.

The implementation MAY reject files that are not valid UTF-8.

### 2.2 Hash

A content hash is:

```text
sha256:<64 lowercase hexadecimal characters>
```

For bytes `b`:

```text
H(b) = "sha256:" ++ lowercase_hex(SHA256(b))
```

### 2.3 Paths

Let `FILE` be the managed target file.

The sidecar directory is:

```text
dirname(FILE) / ("." ++ basename(FILE) ++ ".stile")
```

Example:

```text
notes/todo.txt -> notes/.todo.txt.stile
```

The target file MUST be a regular file. v0 MUST reject directories, symlinks as targets unless explicitly resolved by implementation policy, device files, FIFOs, and sockets.

Recommended policy: resolve symlinks before management and manage the real path.

## 3. Sidecar layout

The implementation MUST create this layout:

```text
.FILE.stile/
  lock
  state.json
  bases/
  conflicts/
  tmp/
```

Base snapshots are stored content-addressed:

```text
bases/<sha256-hex>
```

For hash:

```text
sha256:abcdef...
```

The base path is:

```text
bases/abcdef...
```

Conflict directories are:

```text
conflicts/<conflict-id>/
  meta.json
  base
  current
  proposed
  merged
```

`merged` SHOULD contain conflict markers if available.

## 4. State file

`state.json` MUST be valid UTF-8 JSON.

Minimal schema:

```json
{
  "format_version": 1,
  "target_path": "../file.txt",
  "last_known_sha": "sha256:...",
  "pending_conflict": null
}
```

When a conflict is pending:

```json
{
  "format_version": 1,
  "target_path": "../file.txt",
  "last_known_sha": "sha256:...",
  "pending_conflict": {
    "id": "uuid-or-opaque-id",
    "base_sha": "sha256:...",
    "current_sha": "sha256:...",
    "proposed_sha": "sha256:...",
    "path": ".file.txt.stile/conflicts/<id>"
  }
}
```

`last_known_sha` is advisory. The current file hash is always obtained by reading `FILE`.

## 5. Locking

Every command that mutates sidecar state or the target file MUST acquire an exclusive advisory lock on:

```text
.FILE.stile/lock
```

The lock protects:

```text
state.json
bases/
conflicts/
tmp/
FILE replacement
```

The implementation MUST NOT rely on locking `FILE` itself, because atomic replacement changes the inode.

Commands that only read MAY avoid the lock, but `open`, `save`, `resolve`, and `init` MUST lock.

## 6. Atomic file replacement

To replace `FILE` with bytes `b`, the implementation MUST:

1. Create a temp file inside `.FILE.stile/tmp/`.
2. Write all bytes `b` to the temp file.
3. Flush user-space buffers.
4. `fsync` the temp file.
5. Apply the target file mode bits to the temp file.
6. Rename the temp file over `FILE` using same-filesystem atomic rename.
7. `fsync` the parent directory of `FILE`.

The implementation SHOULD preserve permissions from the existing file. It SHOULD preserve owner and group when permitted. It MAY ignore extended attributes in v0.

If any step fails before rename, `FILE` MUST remain unchanged.

## 7. Commands

## 7.1 `stile init FILE`

### Behavior

`init` creates the sidecar layout if absent.

Algorithm:

```text
ensure FILE exists and is a regular UTF-8 text file
create sidecar directories
acquire sidecar lock
read FILE as bytes current
current_sha = H(current)
store_base(current)
write state.json with last_known_sha = current_sha and pending_conflict = null
release lock
```

If the sidecar already exists, `init` MUST be idempotent unless the sidecar is corrupt.

### JSON output

With `--json`:

```json
{
  "status": "ok",
  "file": "file.txt",
  "sha": "sha256:...",
  "sidecar": ".file.txt.stile"
}
```

## 7.2 `stile open FILE`

### Behavior

`open` captures a base snapshot of the current target file.

Algorithm:

```text
ensure sidecar exists, or create it if auto-init is enabled
acquire sidecar lock
read FILE as bytes base
base_sha = H(base)
store_base(base)
read state.json
release lock
return base_sha and base_path
```

`open` MUST store a base snapshot before returning.

### JSON output

```json
{
  "status": "ok",
  "file": "file.txt",
  "base_sha": "sha256:...",
  "base_path": ".file.txt.stile/bases/<hex>",
  "conflicted": false
}
```

If a conflict is pending:

```json
{
  "status": "ok",
  "file": "file.txt",
  "base_sha": "sha256:...",
  "base_path": ".file.txt.stile/bases/<hex>",
  "conflicted": true,
  "pending_conflict": {
    "id": "...",
    "path": ".file.txt.stile/conflicts/..."
  }
}
```

### Safety note

A race-free editor integration MUST load the buffer from `base_path` or from an equivalent `stile` output representing that exact snapshot. It MUST NOT separately read `FILE` after `open` and assume it is the same content.

## 7.3 `stile save FILE --base-sha HASH [--actor ACTOR] < PROPOSED`

### Behavior

`save` attempts to replace `FILE` with `PROPOSED`, using `HASH` as the caller's base snapshot.

Preconditions:

```text
sidecar exists
HASH is syntactically valid
base snapshot bases/<hex(HASH)> exists
no pending conflict exists
stdin contains valid supported text
```

If a pending conflict exists, `save` MUST reject with `ConflictPending`.

### Algorithm

Let:

```text
base      = read_base(HASH)
proposed  = read_stdin()
current   = read(FILE)
base_sha  = HASH
prop_sha  = H(proposed)
curr_sha  = H(current)
```

Under the sidecar lock:

```text
if pending_conflict != null:
    reject ConflictPending

if prop_sha == curr_sha:
    store_base(current)
    update last_known_sha = curr_sha
    return saved noop

if curr_sha == base_sha:
    atomic_replace(FILE, proposed)
    store_base(proposed)
    update last_known_sha = prop_sha
    return saved direct

else:
    result = merge3(base, current, proposed)
    if result = Clean(merged):
        merged_sha = H(merged)
        atomic_replace(FILE, merged)
        store_base(merged)
        update last_known_sha = merged_sha
        return saved merged
    if result = Conflict(conflict_data):
        create_conflict(base, current, proposed, conflict_data)
        update pending_conflict
        leave FILE unchanged
        return conflict
```

### JSON output on success

```json
{
  "status": "saved",
  "mode": "direct",
  "sha": "sha256:..."
}
```

`mode` MUST be one of:

```text
direct
merged
noop
```

### JSON output on conflict

```json
{
  "status": "conflict",
  "conflict_id": "...",
  "conflict_path": ".file.txt.stile/conflicts/<id>",
  "base_sha": "sha256:...",
  "current_sha": "sha256:...",
  "proposed_sha": "sha256:..."
}
```

On conflict, `FILE` MUST remain byte-for-byte equal to `current`.

## 7.4 `stile status FILE`

### Behavior

`status` reports the current file hash and sidecar state.

It SHOULD acquire the lock for coherent output.

### JSON output

When clean:

```json
{
  "status": "clean",
  "file": "file.txt",
  "current_sha": "sha256:...",
  "last_known_sha": "sha256:..."
}
```

When conflicted:

```json
{
  "status": "conflicted",
  "file": "file.txt",
  "current_sha": "sha256:...",
  "pending_conflict": {
    "id": "...",
    "path": ".file.txt.stile/conflicts/..."
  }
}
```

When unmanaged:

```json
{
  "status": "unmanaged",
  "file": "file.txt"
}
```

## 7.5 `stile resolve FILE --conflict-id ID [--actor ACTOR] < RESOLVED`

### Behavior

`resolve` writes a human or tool-provided resolution and clears the pending conflict.

Preconditions:

```text
sidecar exists
pending_conflict exists
ID equals pending_conflict.id
stdin contains valid supported text
```

Algorithm under lock:

```text
read RESOLVED from stdin
resolved_sha = H(RESOLVED)
atomic_replace(FILE, RESOLVED)
store_base(RESOLVED)
set last_known_sha = resolved_sha
set pending_conflict = null
return resolved
```

### JSON output

```json
{
  "status": "resolved",
  "file": "file.txt",
  "sha": "sha256:..."
}
```

## 8. Merge specification

The merge function is:

```text
merge3(base, current, proposed) -> Clean(bytes) | Conflict(data)
```

Meanings:

```text
base     = content observed by the actor when editing began
current  = content currently on disk
proposed = actor's new candidate content
```

Required property:

```text
If current == base, merge3 is not called.
If proposed == current, merge3 is not called.
If current and proposed make non-overlapping line-based edits from base, merge3 SHOULD return Clean.
If current and proposed make incompatible overlapping line-based edits from base, merge3 MUST return Conflict or a clean result that is equivalent to a conservative 3-way merge.
```

v0 MAY implement merge by invoking POSIX/GNU `diff3` or by using an internal deterministic 3-way line merge.

If using `diff3`, the conceptual argument order is:

```text
diff3 proposed base current
```

where `base` is the common ancestor.

The implementation MUST treat a merge tool error separately from a content conflict.

## 9. Exit codes

Recommended exit codes:

```text
0 success
1 merge conflict
2 usage error
3 unmanaged or corrupt sidecar
4 unknown base
5 pending conflict
6 I/O error
7 merge tool error
```

If the implementation chooses different numeric codes, it MUST document them and keep them stable.

## 10. Error names

The implementation SHOULD use these stable error names in JSON:

```text
UsageError
UnsupportedFile
UnmanagedFile
CorruptSidecar
UnknownBase
ConflictPending
ConflictIdMismatch
IoError
MergeToolError
InvalidUtf8
```

Example:

```json
{
  "status": "error",
  "error": "UnknownBase",
  "message": "base snapshot sha256:... is not present"
}
```

## 11. Race-free protocols

### 11.1 Editor protocol

A race-free editor integration MUST use this sequence:

```text
OPEN:
  response = stile open FILE --json
  buffer = read(response.base_path)
  base_sha = response.base_sha

SAVE:
  response = stile save FILE --base-sha base_sha --actor editor < buffer
  if response.status == saved:
      base_sha = response.sha
      optionally reload buffer from FILE
  if response.status == conflict:
      present response.conflict_path
```

### 11.2 Process protocol

A race-free process integration MUST use this sequence:

```text
response = stile open FILE --json
input = read(response.base_path)
output = compute(input)
stile save FILE --base-sha response.base_sha --actor process < output
```

### 11.3 Forbidden protocol

This is not race-free:

```text
read FILE directly
later call stile open FILE
edit originally read content
save using base from stile open
```

The file could have changed between the direct read and `open`.

## 12. Conflict artifacts

When a conflict occurs, the implementation MUST create:

```text
conflicts/<id>/base
conflicts/<id>/current
conflicts/<id>/proposed
conflicts/<id>/meta.json
```

It SHOULD create:

```text
conflicts/<id>/merged
```

`merged` SHOULD contain a merge attempt with conflict markers.

`meta.json` schema:

```json
{
  "id": "...",
  "actor": "...",
  "base_sha": "sha256:...",
  "current_sha": "sha256:...",
  "proposed_sha": "sha256:...",
  "created_at": "2026-05-02T00:00:00Z"
}
```

Timestamps are informative only. They MUST NOT affect merge semantics.

## 13. Security and robustness

The implementation MUST avoid shell injection when invoking external merge tools.

The implementation MUST create temp files safely. It MUST NOT use predictable temp names without exclusive creation.

The implementation MUST reject path traversal through sidecar-derived paths.

The implementation SHOULD handle crashes as follows:

- If a temp file remains in `tmp/`, it MAY be deleted on the next command.
- If `state.json` is corrupt, mutating commands MUST reject until repaired.
- If a conflict directory exists but state does not reference it, `status` MAY report an orphan conflict warning.

## 14. Conformance tests

A conforming v0 implementation MUST pass these tests.

### T1: init idempotence

Running `init FILE` twice succeeds and preserves the sidecar.

### T2: open stores exact base

After `open`, `base_path` exists and its hash equals `base_sha`.

### T3: direct save

Given file `A`, base `A`, proposed `B`, `save` writes `B` and returns `direct`.

### T4: noop save

Given file `B`, base `A`, proposed `B`, `save` returns `noop` and does not create a conflict.

### T5: stale compatible save

Given:

```text
base:     x\ny\nz\n
current:  x\ny1\nz\n
proposed: x\ny\nz1\n
```

`save` returns `merged` and final file contains both `y1` and `z1`.

### T6: stale conflicting save

Given:

```text
base:     x\ny\nz\n
current:  x\ny-current\nz\n
proposed: x\ny-proposed\nz\n
```

`save` returns conflict, leaves file equal to `current`, and creates conflict artifacts.

### T7: pending conflict blocks save

After T6, ordinary `save` returns `ConflictPending` until `resolve` succeeds.

### T8: resolve clears conflict

After `resolve`, `status` reports clean and the file equals the resolved content.

### T9: unknown base

`save --base-sha sha256:<valid but absent>` returns `UnknownBase`.

### T10: atomicity smoke test

While repeatedly saving large alternating contents, a concurrent reader must never observe a prefix, suffix, or mixed content not equal to one of the complete written versions.

## 15. Implementation notes

Recommended structure:

```text
src/
  main
  cli
  paths
  hash
  lock
  atomic_write
  store
  merge
  commands/
    init
    open
    save
    status
    resolve
```

All correctness-critical behavior belongs in the CLI tool, not in editor plugins.

Editor plugins should be thin wrappers around `open` and `save`.

## 16. Deferred v1 ideas

The following are explicitly outside this spec:

- Event log.
- Reducer-projection architecture.
- Revision numbers.
- Base garbage collection.
- File history.
- Semantic edits.
- Multi-file transactions.
- Daemon mode.
- Network replication.

Do not implement these until v0 is correct and small.
