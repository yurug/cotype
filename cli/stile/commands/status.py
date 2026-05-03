"""`stile status FILE` -- report current hash and sidecar state.

Spec refs: kb/spec/algorithms.md#status
"""
from __future__ import annotations

from stile.errors import IoError
from stile.hash import hash_bytes
from stile.lock import sidecar_lock
from stile.paths import resolve_target, sidecar_dir
from stile.store import read_state, state_exists


def cmd_status(file_arg: str) -> dict:
    """Return one of: unmanaged | clean | conflicted (each with relevant fields)."""
    file = resolve_target(file_arg)
    sidecar = sidecar_dir(file)
    if not state_exists(sidecar):
        return {"status": "unmanaged", "file": str(file)}
    # Locking is not strictly required for read-only output, but it gives a
    # coherent snapshot if a concurrent save is in progress.
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
