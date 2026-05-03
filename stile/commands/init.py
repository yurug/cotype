"""`stile init FILE` -- create sidecar layout and capture the first base.

Spec refs: kb/spec/algorithms.md#init
Properties enforced: P11 (idempotent), P5 (byte-exact hash), P6 (locked).
"""
from __future__ import annotations

from stile.errors import InvalidUtf8, IoError
from stile.hash import hash_bytes
from stile.lock import sidecar_lock
from stile.paths import relpath_from_sidecar, resolve_target, sidecar_dir
from stile.store import (
    State,
    ensure_layout,
    read_state,
    state_exists,
    store_base,
    write_state,
)


def cmd_init(file_arg: str) -> dict:
    """Initialise the sidecar for `file_arg`. Idempotent."""
    file = resolve_target(file_arg)
    sidecar = sidecar_dir(file)
    ensure_layout(sidecar)
    with sidecar_lock(sidecar):
        try:
            content = file.read_bytes()
        except OSError as e:
            raise IoError(f"reading {file}: {e}") from e
        try:
            content.decode("utf-8")
        except UnicodeDecodeError as e:
            raise InvalidUtf8(f"{file} is not valid UTF-8") from e
        sha = hash_bytes(content)
        store_base(sidecar, content, sha)
        if state_exists(sidecar):
            # Idempotent path: validate format_version, refresh advisory fields.
            st = read_state(sidecar)
            st.last_known_sha = sha
            st.target_path = relpath_from_sidecar(file, sidecar)
        else:
            st = State(
                target_path=relpath_from_sidecar(file, sidecar),
                last_known_sha=sha,
                pending_conflict=None,
            )
        write_state(sidecar, st)
    return {
        "status": "ok",
        "file": str(file),
        "sha": sha,
        "sidecar": str(sidecar),
    }
