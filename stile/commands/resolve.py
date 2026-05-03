"""`stile resolve FILE --conflict-id ID < resolved` -- accept resolved content.

Spec refs: kb/spec/algorithms.md#resolve
Properties enforced: P4 (cleanup post-resolve), P12, P-path-traversal-safety.
"""
from __future__ import annotations

from stile.atomic_write import atomic_replace
from stile.errors import (
    ConflictIdMismatch,
    InvalidUtf8,
    UnmanagedFile,
    UsageError,
)
from stile.hash import hash_bytes
from stile.lock import sidecar_lock
from stile.paths import CONFLICT_ID_RE, resolve_target, sidecar_dir
from stile.store import read_state, state_exists, store_base, write_state


def cmd_resolve(
    file_arg: str, conflict_id: str, actor: str, resolved: bytes
) -> dict:
    """Write `resolved` and clear `state.pending_conflict`."""
    file = resolve_target(file_arg)
    sidecar = sidecar_dir(file)
    if not state_exists(sidecar):
        raise UnmanagedFile(f"{file} is not managed by stile")
    # Validate the id BEFORE it can flow into any filesystem path.
    if not CONFLICT_ID_RE.match(conflict_id):
        raise UsageError(
            f"invalid conflict id {conflict_id!r} (must be 32 lowercase hex chars)"
        )
    try:
        resolved.decode("utf-8")
    except UnicodeDecodeError as e:
        raise InvalidUtf8("resolved content is not valid UTF-8") from e

    with sidecar_lock(sidecar):
        st = read_state(sidecar)
        if st.pending_conflict is None:
            raise UsageError("no pending conflict to resolve")
        if st.pending_conflict.id != conflict_id:
            raise ConflictIdMismatch(
                f"pending conflict id is {st.pending_conflict.id}, "
                f"not {conflict_id}"
            )
        sha = hash_bytes(resolved)
        atomic_replace(file, resolved, sidecar)
        store_base(sidecar, resolved, sha)
        st.last_known_sha = sha
        st.pending_conflict = None
        write_state(sidecar, st)
    # `actor` is informational only; we do not record it on resolve in v0.
    _ = actor
    return {"status": "resolved", "file": str(file), "sha": sha}
