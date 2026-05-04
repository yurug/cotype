"""`stile resolve FILE --conflict-id ID < resolved` -- accept resolved content.

Spec refs: kb/spec/algorithms.md#resolve
Properties enforced: P4 (cleanup post-resolve), P12, P-path-traversal-safety.

Two equivalent forms:

  Explicit:    stile resolve FILE --conflict-id ID < resolved_bytes
  Shorthand:   stile resolve FILE --use-merged
               (reads <sidecar>/conflicts/<id>/merged after the user has
                edited it to remove conflict markers; refuses otherwise.)
"""
from __future__ import annotations

from stile.atomic_write import atomic_replace
from stile.errors import (
    ConflictIdMismatch,
    InvalidUtf8,
    IoError,
    UnmanagedFile,
    UsageError,
)
from stile.hash import hash_bytes
from stile.lock import sidecar_lock
from stile.paths import CONFLICT_ID_RE, conflict_dir, resolve_target, sidecar_dir
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


def cmd_resolve(
    file_arg: str,
    conflict_id: str | None = None,
    actor: str = "unknown",
    resolved: bytes | None = None,
    *,
    use_merged: bool = False,
) -> dict:
    """Write `resolved` and clear `state.pending_conflict`.

    Two forms:
        explicit:  pass `conflict_id` and `resolved` (caller-supplied bytes).
        shorthand: pass `use_merged=True`; both id and bytes come from the
                   pending conflict directory's `merged` file.
    """
    file = resolve_target(file_arg)
    sidecar = sidecar_dir(file)
    if not state_exists(sidecar):
        raise UnmanagedFile(f"{file} is not managed by stile")

    # Pre-lock validation: argument shape only. Anything that depends on the
    # current state.json is checked under the lock below.
    if use_merged:
        if conflict_id is not None or resolved is not None:
            raise UsageError(
                "--use-merged cannot be combined with --conflict-id or stdin"
            )
    else:
        if conflict_id is None:
            raise UsageError(
                "resolve requires --conflict-id ID (or --use-merged)"
            )
        if resolved is None:
            raise UsageError("resolve requires resolved bytes on stdin")
        if not CONFLICT_ID_RE.match(conflict_id):
            raise UsageError(
                f"invalid conflict id {conflict_id!r} "
                f"(must be 32 lowercase hex chars)"
            )
        try:
            resolved.decode("utf-8")
        except UnicodeDecodeError as e:
            raise InvalidUtf8("resolved content is not valid UTF-8") from e

    with sidecar_lock(sidecar):
        st = read_state(sidecar)
        if st.pending_conflict is None:
            raise UsageError("no pending conflict to resolve")

        if use_merged:
            # Derive id from state and read the merged file.
            conflict_id = st.pending_conflict.id
            cdir = conflict_dir(sidecar, conflict_id)
            merged_path = cdir / "merged"
            if not merged_path.exists():
                raise IoError(
                    f"merged file missing at {merged_path}; "
                    f"supply a resolution via stdin with --conflict-id instead"
                )
            try:
                resolved = merged_path.read_bytes()
            except OSError as e:
                raise IoError(f"reading {merged_path}: {e}") from e
            if _has_conflict_markers(resolved):
                raise UsageError(
                    f"{merged_path} still contains conflict markers; "
                    f"edit it to resolve them, then re-run "
                    f"`stile resolve --use-merged`"
                )
            try:
                resolved.decode("utf-8")
            except UnicodeDecodeError as e:
                raise InvalidUtf8(
                    f"{merged_path} is not valid UTF-8"
                ) from e
        elif st.pending_conflict.id != conflict_id:
            raise ConflictIdMismatch(
                f"pending conflict id is {st.pending_conflict.id}, "
                f"not {conflict_id}"
            )

        # By here, `resolved` is non-None and UTF-8-validated.
        assert resolved is not None
        sha = hash_bytes(resolved)
        atomic_replace(file, resolved, sidecar)
        store_base(sidecar, resolved, sha)
        st.last_known_sha = sha
        st.pending_conflict = None
        write_state(sidecar, st)
    # `actor` is informational only; we do not record it on resolve.
    _ = actor
    return {"status": "resolved", "file": str(file), "sha": sha}
