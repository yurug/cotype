"""`stile resolve FILE` -- accept the user's hand-edit of FILE.

Spec refs: kb/spec/algorithms.md#resolve
Properties enforced: P4 (cleanup post-resolve), P12.

The flow is git-style: a conflict from `stile save` left FILE containing
diff3 markers. The user opens FILE in their editor, removes the markers,
and saves the buffer. Then `stile resolve FILE` validates that no markers
remain, snapshots FILE as the new base, and clears the pending conflict.
"""
from __future__ import annotations

from stile.errors import InvalidUtf8, IoError, UnmanagedFile, UsageError
from stile.hash import hash_bytes
from stile.lock import sidecar_lock
from stile.paths import resolve_target, sidecar_dir
from stile.store import read_state, state_exists, store_base, write_state


def _has_conflict_markers(content: bytes) -> bool:
    """Detect leftover diff3 conflict markers.

    We require BOTH a `<<<<<<< ` opener AND a `>>>>>>> ` closer line prefix.
    The conjunction is essentially impossible in genuine text -- a lone
    `=======` line is plausible Markdown (Setext H1 underline) and would
    false-positive on its own.
    """
    has_open = False
    has_close = False
    for line in content.splitlines():
        if line.startswith(b"<<<<<<< "):
            has_open = True
        if line.startswith(b">>>>>>> "):
            has_close = True
        if has_open and has_close:
            return True
    return False


def cmd_resolve(file_arg: str, actor: str = "unknown") -> dict:
    """Read FILE, validate no markers, clear `state.pending_conflict`."""
    file = resolve_target(file_arg)
    sidecar = sidecar_dir(file)
    if not state_exists(sidecar):
        raise UnmanagedFile(f"{file} is not managed by stile")

    with sidecar_lock(sidecar):
        st = read_state(sidecar)
        if st.pending_conflict is None:
            raise UsageError("no pending conflict to resolve")

        try:
            content = file.read_bytes()
        except OSError as e:
            raise IoError(f"reading {file}: {e}") from e
        try:
            content.decode("utf-8")
        except UnicodeDecodeError as e:
            raise InvalidUtf8(f"{file} is not valid UTF-8") from e
        if _has_conflict_markers(content):
            raise UsageError(
                f"{file} still contains conflict markers; "
                f"edit them out and re-run `stile resolve`"
            )

        sha = hash_bytes(content)
        store_base(sidecar, content, sha)
        st.last_known_sha = sha
        st.pending_conflict = None
        write_state(sidecar, st)
    # `actor` is informational only; we do not record it on resolve.
    _ = actor
    return {"status": "resolved", "file": str(file), "sha": sha}
