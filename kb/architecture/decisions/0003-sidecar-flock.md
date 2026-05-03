---
id: adr-0003
type: decision
summary: ADR-0003 — serialise mutating commands with flock on `<sidecar>/lock`, not on FILE.
domain: architecture
last-updated: 2026-05-02
depends-on: []
refines: []
related: [architecture-overview, external-posix-fs, properties-functional]
---

# ADR-0003: Advisory flock on the sidecar `lock` file

## Context

Multiple commands mutate sidecar state and `FILE`. Without serialisation, two `save`s racing on the same file violate P1 and P4: both see `pending_conflict == null`, both decide direct-write, last-writer-wins.

We need a cooperative mutex with these properties:
- Held for the duration of one command's mutation.
- Released on every exit path (success, error, exception, signal-induced exit).
- Survives across processes (not just threads).
- Doesn't break atomic_replace.

POSIX offers two main primitives: `fcntl.flock` (advisory, file-handle-scoped) and `fcntl.lockf` (advisory, byte-range, can interact poorly with `os.replace`). Locking `FILE` itself is broken because atomic-rename swaps the inode under the lock holder — every reader/writer would race the rename.

## Decision

- Each sidecar contains an empty `lock` file: `<sidecar>/lock`.
- Mutating commands acquire `fcntl.flock(fd, LOCK_EX)` on that fd at the top of the call chain (in `commands/*`), and release on exit via `contextmanager`.
- Read-only commands (`status`) MAY acquire the lock for a coherent snapshot; not strictly required.

## Consequences

Positive:
- Lock is independent of FILE's inode, so atomic_replace works fine under the lock.
- Cleanup is automatic: when the holding process exits, the kernel releases the flock.
- Cross-process serialisation, not just intra-process.

Negative:
- Advisory only — a misbehaving program that doesn't acquire the flock can still race. Documented; out of v0 threat model.
- Doesn't work over NFS in older kernels; in v0 we're local-only.

Rejected alternatives:
- **`fcntl.lockf`**: byte-range locks have surprising interactions with `os.replace` and `dup2`. flock is simpler.
- **Lock on FILE itself**: broken under atomic-rename (the inode changes).
- **Lockfile + sentinel**: re-implementing what flock does, with worse failure modes.

## What this means for implementers

- The flock context manager lives in `lock.py` and looks like:
  ```python
  @contextmanager
  def sidecar_lock(sidecar_dir: Path) -> Iterator[None]:
      lock_path = sidecar_dir / "lock"
      lock_path.touch(exist_ok=True)
      with open(lock_path, "rb") as fd:
          fcntl.flock(fd.fileno(), fcntl.LOCK_EX)
          try:
              yield
          finally:
              fcntl.flock(fd.fileno(), fcntl.LOCK_UN)
  ```
- Every command function in `commands/*` wraps its body in `with sidecar_lock(sidecar): ...`.
- Lower layers (`store`, `atomic_write`) assume the caller holds the lock. They MUST NOT acquire it themselves (would deadlock).

## Reconsider when

We add network synchronisation or daemon mode. Both are explicitly out of v0 (PRD §5).

## Related files
- `../overview.md`
- `../../external/posix-fs.md` — flock semantics
- `../../properties/functional.md` — P6
