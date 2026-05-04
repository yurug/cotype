"""`cotype open FILE` -- capture a fresh base snapshot.

Spec refs: kb/spec/algorithms.md#open
Properties enforced: P5, P6, P15 (returned base_path hashes to base_sha).
"""
from __future__ import annotations

from cotype.errors import InvalidUtf8, IoError
from cotype.hash import hash_bytes
from cotype.lock import sidecar_lock
from cotype.paths import relpath_from_sidecar, resolve_target, sidecar_dir
from cotype.store import (
    State,
    ensure_layout,
    read_state,
    state_exists,
    store_base,
    write_state,
)


def cmd_open(file_arg: str) -> dict:
    """Capture a fresh base snapshot. Auto-inits the sidecar if absent."""
    file = resolve_target(file_arg)
    sidecar = sidecar_dir(file)
    ensure_layout(sidecar)  # auto-init: idempotent dir creation
    with sidecar_lock(sidecar):
        try:
            content = file.read_bytes()
        except OSError as e:
            raise IoError(f"reading {file}: {e}") from e
        # Open enforces UTF-8 too: any subsequent save would reject anyway,
        # and storing a base of unsupported bytes silently is misleading.
        try:
            content.decode("utf-8")
        except UnicodeDecodeError as e:
            raise InvalidUtf8(f"{file} is not valid UTF-8") from e
        sha = hash_bytes(content)
        bp = store_base(sidecar, content, sha)
        if state_exists(sidecar):
            st = read_state(sidecar)
            st.last_known_sha = sha
            st.target_path = relpath_from_sidecar(file, sidecar)
        else:
            st = State(
                target_path=relpath_from_sidecar(file, sidecar),
                last_known_sha=sha,
            )
        write_state(sidecar, st)
        result: dict = {
            "status": "ok",
            "file": str(file),
            "base_sha": sha,
            "base_path": str(bp),
            "conflicted": st.pending_conflict is not None,
        }
        if st.pending_conflict is not None:
            result["pending_conflict"] = {
                "id": st.pending_conflict.id,
                "path": st.pending_conflict.path,
            }
        return result
