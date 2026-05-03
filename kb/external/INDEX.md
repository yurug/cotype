---
id: external-index
type: index
summary: Routing for third-party / OS-level dependencies and their actual runtime behaviour.
domain: external
last-updated: 2026-05-02
depends-on: []
refines: []
related: [index]
---

# External — Index

## One-liner
What stile depends on outside Python stdlib, with documented runtime behaviour.

## Files

- `diff3.md` — POSIX `diff3 -m`. Used by `merge.py`. Argument order, exit codes, conflict-marker format.
- `posix-fs.md` — `os.replace`, `os.fsync`, `fcntl.flock`. Used by `atomic_write.py`, `lock.py`. Atomicity and durability semantics.

## Request budget summary

| Operation       | External calls per invocation               |
|-----------------|---------------------------------------------|
| `init`          | 0 subprocesses; ~3 fsyncs                   |
| `open`          | 0 subprocesses; ~2 fsyncs                   |
| `save` (direct) | 0 subprocesses; ~3 fsyncs                   |
| `save` (merged) | 1 `diff3`; ~4 fsyncs                        |
| `save` (noop)   | 0 subprocesses; ~1 fsync (state.json only)  |
| `save` (conflict) | 1 `diff3`; ~5 fsyncs (state + conflict files) |
| `status`        | 0 subprocesses; 0 fsyncs (read-only)        |
| `resolve`       | 0 subprocesses; ~3 fsyncs                   |

This stays well under "100 calls for a basic operation" — no need for batching/joining.

## Agent notes
> Add a new entry here whenever you introduce a new external dep. ADR-0001 says justify any third-party Python lib.

## Related files
- `../architecture/overview.md`
- `../architecture/decisions/`
