"""`cotype status FILE' -- read-only state report.

What `status' returns
=====================

One of three top-level shapes, distinguished by the `status' field:

    {"status": "unmanaged", "file": ...}                -- no sidecar.

    {"status": "clean",                                 -- sidecar OK,
     "file": ...,                                          no pending
     "current_sha": "sha256:...",                          conflict.
     "last_known_sha": "sha256:..."}

    {"status": "conflicted",                            -- sidecar OK,
     "file": ...,                                          a conflict
     "current_sha": "sha256:...",                          is pending.
     "pending_conflict": {"id": ..., "path": ...}}

Why `current_sha' is included for `clean' AND `conflicted': callers
that want to detect "did anything change since the last open?"
without a fresh `cotype open' (which would create a new base) can
poll status and compare. It's also useful for "is the file the same
bytes the sidecar last saw?" (compare current_sha to last_known_sha).

Why we still take the lock
==========================

Strictly, status is read-only: the sidecar lock isn't *required* for
correctness here. We take it anyway for two reasons:

  1. **Coherent snapshot.** Without the lock, status could read
     `state.json' just as a concurrent `cotype save' is mid-write,
     and report a state that doesn't quite match reality (or, worse,
     a `CorruptSidecar' from observing a torn write). The lock
     guarantees we see one consistent snapshot.

  2. **No false negatives on `conflicted'.** A status check that
     missed a pending conflict because of a race would be a
     particularly bad UX -- the user would think the file was clean,
     try a save, and hit `ConflictPending' on the very next call.

The lock is exclusive (we don't take a shared lock here) for
simplicity. The cost is microseconds; a future optimization could
introduce LOCK_SH for status, but the gain isn't worth the
complexity today.

Spec refs: kb/spec/algorithms.md#status
"""
from __future__ import annotations

from cotype.errors import IoError
from cotype.hash import hash_bytes
from cotype.lock import sidecar_lock
from cotype.paths import resolve_target, sidecar_dir
from cotype.store import read_state, state_exists


def cmd_status(file_arg: str) -> dict:
    """Return one of: unmanaged | clean | conflicted, with the relevant fields.

    Side-effect free: never writes anywhere, never modifies state.
    Safe to poll on a tight loop; one caller's poll cannot disrupt
    another caller's save (besides the brief lock contention).
    """
    file = resolve_target(file_arg)
    sidecar = sidecar_dir(file)
    if not state_exists(sidecar):
        # Fast-path: no sidecar means the file is just a regular
        # text file, not under cotype management. Don't bother
        # taking a lock that doesn't exist.
        return {"status": "unmanaged", "file": str(file)}
    # Take the lock for a coherent snapshot. Cheap (microseconds);
    # avoids the "torn write seen by a status reader" race.
    with sidecar_lock(sidecar):
        st = read_state(sidecar)
        try:
            content = file.read_bytes()
        except OSError as e:
            raise IoError(f"reading {file}: {e}") from e
        current_sha = hash_bytes(content)
    if st.pending_conflict is not None:
        return {
            "status": "conflicted",
            "file": str(file),
            "current_sha": current_sha,
            "pending_conflict": {
                "id": st.pending_conflict.id,
                "path": st.pending_conflict.path,
            },
        }
    return {
        "status": "clean",
        "file": str(file),
        "current_sha": current_sha,
        "last_known_sha": st.last_known_sha,
    }
