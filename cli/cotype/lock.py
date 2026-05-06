"""Advisory exclusive lock on `<sidecar>/lock`.

Why locking, why advisory, and why the sidecar
==============================================

Every cotype command that mutates state (init, open, save, resolve)
acquires an exclusive `flock` on `<sidecar>/lock` for the duration of
its mutation. Two parallel `cotype save` invocations on the same FILE
serialise on this lock; one runs to completion (a clean direct write,
say), the other then takes the lock, sees the new state on disk, and
classifies its own attempt against the now-current bytes (typically
becoming a 3-way merge).

P6 (functional properties): "Mutating commands hold the sidecar lock."

Three design choices worth being explicit about:

(1) Advisory (flock), not mandatory.

    Mandatory locking on Linux requires a setgid filesystem mount and
    is rarely available; macOS doesn't support it at all. cotype's
    locking is *cooperative*: any process that follows the protocol
    serialises correctly, but a misbehaving process that writes to
    FILE directly without taking the lock breaks the contract. That
    misbehaving process is exactly what the PRD's "no actor writes
    FILE directly during managed operation" rule prohibits, so we
    accept advisory and document it.

(2) Locked file is `<sidecar>/lock`, NOT `FILE` itself.

    Atomic replacement of FILE swaps its inode (the new bytes live
    at a brand-new inode after `os.replace'). Any flock held on the
    OLD inode would be invalidated by the rename. So we lock a
    secondary file that we never replace -- `<sidecar>/lock' -- and
    its inode stays stable across saves.

(3) Exclusive only -- no shared/read locks.

    Status reporting (`cotype status') is read-only and *recommended*
    to take the lock for a coherent snapshot, but doesn't strictly
    need to. We could add LOCK_SH for a slightly cheaper status
    path, but the saving in practice is microseconds and the
    complexity of mixed-mode locking isn't worth it. Today every
    caller that takes a lock takes it exclusively.

Spec refs: kb/architecture/decisions/0003-sidecar-flock.md
Properties enforced: P6
"""
from __future__ import annotations

import fcntl
from contextlib import contextmanager
from pathlib import Path
from typing import Iterator

from cotype.errors import IoError


@contextmanager
def sidecar_lock(sidecar: Path) -> Iterator[None]:
    """Hold an exclusive `flock` on `<sidecar>/lock' for the body of the block.

    Usage::

        with sidecar_lock(sidecar):
            ...mutate state.json, write a base, etc...

    Creates the lock file if absent (a fresh `cotype init' is the
    first place this happens). The fd is closed on exit, which the
    kernel turns into a lock release automatically -- so even an
    uncaught exception inside the block cannot leak the lock past
    process exit.

    Subtleties:

    - `flock(LOCK_EX)` on a process already holding the lock for the
      same fd is a no-op; on a different fd (same file), it would
      block forever. Cotype's command flow is strictly non-reentrant
      with respect to this lock -- no `cmd_save' calls another
      command that would re-take the lock. If you add a new code
      path here, keep it that way.

    - Other cotype processes block, they don't fail. There's no
      `LOCK_NB' anywhere; if two `cotype save' calls happen at the
      same time, the second one waits its turn rather than reporting
      an error.
    """
    lock_path = sidecar / "lock"

    # Ensure the lock file exists. Idempotent on every other call;
    # only meaningful on the very first one (during `cotype init').
    try:
        sidecar.mkdir(parents=True, exist_ok=True)
        lock_path.touch(exist_ok=True)
    except OSError as e:
        raise IoError(f"could not prepare lock file {lock_path}: {e}") from e

    try:
        fd = open(lock_path, "rb")
    except OSError as e:
        raise IoError(f"could not open lock file {lock_path}: {e}") from e

    try:
        # LOCK_EX without LOCK_NB blocks until we get the lock. That's
        # the desired behaviour for serialising concurrent cotype
        # commands -- no one should fail because they had to wait.
        try:
            fcntl.flock(fd.fileno(), fcntl.LOCK_EX)
        except OSError as e:
            raise IoError(f"flock on {lock_path} failed: {e}") from e
        try:
            yield
        finally:
            # Best-effort explicit unlock. Closing the fd would also
            # release it (`close()` implies LOCK_UN on Linux), but
            # an explicit unlock makes the order of events a bit
            # easier to reason about under signals.
            try:
                fcntl.flock(fd.fileno(), fcntl.LOCK_UN)
            except OSError:
                pass
    finally:
        # Always close, even if we raised in the body. The OS releases
        # any remaining lock as a side effect; this is the belt that
        # protects us from a kill-9 between LOCK_UN and the close().
        fd.close()
