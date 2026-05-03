"""Atomic file replacement: tmp -> fsync -> rename -> fsync(parent).

Spec refs: kb/spec/algorithms.md#atomic-replace, kb/external/posix-fs.md
Properties enforced: P2 (atomic visibility), P12 (atomic replace), P13 (mode
preservation).

The temp file MUST live on the same filesystem as the target so that
`os.replace` is an atomic rename. We put it inside `<sidecar>/tmp/` because
the sidecar is co-located with FILE.
"""
from __future__ import annotations

import os
import shutil
import tempfile
from pathlib import Path

from stile.errors import IoError
from stile.paths import tmp_dir


def atomic_replace(target: Path, content: bytes, sidecar: Path) -> None:
    """Replace `target` with `content` atomically.

    Caller MUST already hold the sidecar flock (ADR-0003). Lower layers
    deliberately do not acquire the lock -- that would be a deadlock.

    Steps (and the property each one enforces):
        1. Create a temp file inside <sidecar>/tmp/   (P12: same fs)
        2. Write all bytes; flush user-space buffer.
        3. fsync(temp)                                (P2: durability of contents)
        4. Copy mode bits from target to temp.        (P13)
        5. Try chown(uid, gid); ignore PermissionError (non-root case).
        6. os.replace(temp, target)                   (P2/P12: atomic rename)
        7. fsync(parent dir)                          (P2: durability of name)

    On any OSError before step 6, `target` remains untouched.
    """
    tmp = tmp_dir(sidecar)
    try:
        tmp.mkdir(parents=True, exist_ok=True)
    except OSError as e:
        raise IoError(f"could not prepare tmp dir {tmp}: {e}") from e

    # mkstemp gives us an unguessable filename + exclusive create -- no
    # predictable-name temp races (kb/runbooks/audit-checklist.md section C).
    try:
        fd, tmp_name = tempfile.mkstemp(prefix="atomic-", dir=str(tmp))
    except OSError as e:
        raise IoError(f"could not create temp file in {tmp}: {e}") from e

    tmp_path = Path(tmp_name)
    try:
        with os.fdopen(fd, "wb") as f:
            f.write(content)
            f.flush()
            os.fsync(f.fileno())

        # Preserve permissions only when target already exists.
        if target.exists():
            try:
                shutil.copymode(target, tmp_path)
            except OSError:
                # Mode preservation is best-effort; do not fail the save.
                pass
            try:
                st = target.stat()
                os.chown(tmp_path, st.st_uid, st.st_gid)
            except (PermissionError, OSError):
                # chown requires CAP_CHOWN or matching uid; skip silently.
                pass

        os.replace(tmp_path, target)

        # fsync the directory entry so the rename itself survives a crash.
        # On Linux/macOS opening the dir for reading and fsync'ing is the
        # documented incantation. Best-effort: skip if the dir cannot be
        # opened (rare; would imply a permission problem we can't fix here).
        parent = target.parent
        try:
            dir_fd = os.open(parent, os.O_RDONLY)
        except OSError:
            return
        try:
            os.fsync(dir_fd)
        finally:
            os.close(dir_fd)
    except OSError as e:
        # If we never reached os.replace, the temp may still exist; tidy up.
        try:
            tmp_path.unlink(missing_ok=True)
        except OSError:
            pass
        raise IoError(f"atomic replace of {target} failed: {e}") from e
