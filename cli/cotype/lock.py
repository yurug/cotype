"""Advisory exclusive lock on `<sidecar>/lock`.

Spec refs: kb/architecture/decisions/0003-sidecar-flock.md
Properties enforced: P6 -- mutating commands serialise on this lock.

Why we lock the sidecar's `lock` file (and never `FILE` itself): atomic
replacement swaps FILE's inode, which would invalidate any lock held on
the old inode. The sidecar's `lock` file is never replaced; its inode is
stable, so locking it serialises everything that touches the sidecar.
"""
from __future__ import annotations

import fcntl
from contextlib import contextmanager
from pathlib import Path
from typing import Iterator

from cotype.errors import IoError


@contextmanager
def sidecar_lock(sidecar: Path) -> Iterator[None]:
    """Hold an exclusive flock on `<sidecar>/lock` for the body of the block.

    Creates the lock file if absent. The fd is closed on exit, which releases
    the kernel-held lock automatically -- so even uncaught exceptions cannot
    leak the lock past process exit.
    """
    lock_path = sidecar / "lock"
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
        try:
            fcntl.flock(fd.fileno(), fcntl.LOCK_EX)
        except OSError as e:
            raise IoError(f"flock on {lock_path} failed: {e}") from e
        try:
            yield
        finally:
            # Best-effort unlock; closing the fd would also release it.
            try:
                fcntl.flock(fd.fileno(), fcntl.LOCK_UN)
            except OSError:
                pass
    finally:
        fd.close()
