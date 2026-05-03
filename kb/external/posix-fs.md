---
id: external-posix-fs
type: external
summary: POSIX filesystem primitives we depend on — atomic rename, fsync, flock semantics.
domain: external
last-updated: 2026-05-03
depends-on: []
refines: []
related: [adr-0003, spec-algorithms, properties-functional]
---

# External: POSIX filesystem semantics

## One-liner
What `os.replace`, `os.fsync`, and `fcntl.flock` actually guarantee — and where they don't.

## Atomic rename (`os.replace` / `rename(2)`)

- POSIX `rename(2)` is atomic for **same-filesystem** renames: a concurrent reader sees either the old name or the new name; never an in-between.
- Different-filesystem rename is NOT atomic and falls back to copy+unlink (Python's `os.rename` errors `EXDEV`; `shutil.move` would copy).
- That's why our temp file must live in `<sidecar>/tmp/`, which is co-located with `FILE` (sidecar lives next to FILE).

Implication for stile:
```python
tmp_path = Path(sidecar) / "tmp" / f"atomic-{os.getpid()}-{uuid.uuid4().hex}"
# ... write tmp_path ...
os.replace(tmp_path, file_path)   # ATOMIC because same fs
```

`os.replace` succeeds even if `file_path` exists (overwrite); `os.rename` is also atomic but will fail on Windows if dest exists. We use `os.replace`.

## fsync semantics

- `fsync(fd)` blocks until that file's data and metadata are durable on the underlying device.
- After writing the temp file: `fsync(tmp_fd)` ensures the new bytes survive a crash.
- After `os.replace`: `fsync(parent_dir_fd)` ensures the directory entry change survives a crash. Without it, on some filesystems, post-crash you can see the old name pointing to a half-written inode (very rare, but documented).

Order:
1. Write all bytes to temp.
2. `tmp.flush()` then `os.fsync(tmp.fileno())`.
3. `copymode` / `chown` on temp.
4. `os.replace(tmp, target)`.
5. `os.fsync(open(parent_dir, O_RDONLY).fileno())`.

Step 5 requires opening the dir. On Linux: `os.open(parent, os.O_RDONLY)` then `os.fsync(fd)` then `os.close(fd)`. On macOS: same call works. (On Windows it doesn't — out of scope.)

## flock semantics (`fcntl.flock`)

- **Advisory**: only enforced between processes that all call `flock`. A process that ignores the lock can still write the file. Our threat model assumes cooperating actors.
- **File-handle scoped**: closing the fd releases the lock. The kernel releases it automatically on process exit, including SIGKILL.
- **`LOCK_EX`** is exclusive. Blocks until acquired; can be made non-blocking with `LOCK_NB`.
- **Inheritance**: child processes inherit the lock on `fork()`. Not relevant to us (we don't fork while holding the lock).
- **Filesystem support**: works on local Linux/macOS filesystems. Older NFS may silently degrade. v0 is local-only.

Why we lock the **sidecar's** `lock` file rather than `FILE`:
- `FILE` is replaced via `os.replace`, which swaps the inode. The lock-holder is suddenly holding a lock on a stale inode (now unlinked). The replacement is unprotected.
- `<sidecar>/lock` is never replaced; its inode is stable for the sidecar's lifetime. Locking it serialises everything that touches the sidecar.

## tempfile conventions

- `tempfile.NamedTemporaryFile(dir=tmp_dir, delete=False)` is fine — we manage cleanup ourselves (rename consumes the temp).
- Name format: `atomic-<pid>-<uuid>` so leftover stragglers from a crash are easy to identify and clean.

## Permission preservation

- `shutil.copymode(src, dst)` copies mode bits but not owner/group.
- `os.chown(dst, uid, gid)` requires either matching uid (for non-root) or `CAP_CHOWN`. We attempt it and silently swallow `PermissionError`.
- xattrs / ACLs are NOT preserved in v0 (out of scope).

## Cross-platform note

We target Linux + macOS. Windows is out of scope: flock semantics differ (LockFileEx), atomic-rename has different exists-overwrite rules, and parent-dir fsync isn't supported.

## Agent notes
> Forgetting `fsync(parent)` is the most common bug in "atomic save" code; do not omit it.
> If `os.replace` raises `OSError(EXDEV)`, the temp file is on a different filesystem from FILE — investigate the sidecar path computation.
> The advisory nature of flock is a real constraint: documented, accepted. Don't try to upgrade it to mandatory.

## Related files
- `../architecture/decisions/0003-sidecar-flock.md`
- `../spec/algorithms.md#atomic-replace`
- `../properties/functional.md#P12`
