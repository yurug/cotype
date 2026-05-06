"""`cotype open FILE` -- capture a fresh base snapshot.

The race-free read pattern
==========================

The single most important contract of `cotype open' is that it
returns BOTH a `base_sha' (the hash of the captured bytes) AND a
`base_path' (a path to those exact bytes inside the sidecar).
Callers MUST read their working content from `base_path', not by
re-reading FILE separately:

    GOOD:
        meta = cotype open FILE --json
        base_sha  = meta.base_sha
        base_path = meta.base_path
        my_buffer = read(base_path)        # bytes hash to base_sha
        ...edit my_buffer...
        cotype save FILE --base-sha "$base_sha" < my_buffer

    BAD ("forbidden protocol", per kb/spec/protocols.md):
        meta = cotype open FILE --json
        base_sha = meta.base_sha
        my_buffer = read(FILE)             # ← race: another writer
                                           #   could have landed here
        ...edit...
        cotype save FILE --base-sha "$base_sha" < my_buffer

The bad version has a window between `cotype open' and the caller's
`read(FILE)' during which another actor's save could land. That
save's bytes would slip into the caller's buffer without `cotype'
seeing the staleness, and the caller's eventual `save' would happily
overwrite the new content thinking it was on top of `base_sha'.

By reading from `base_path' instead -- where the bytes that were
captured into `base_sha' are pinned -- there is no race window.

P15 (functional properties) enforces this invariant: the bytes at
`base_path' MUST hash to `base_sha'.

What `open' does
================

  1. Resolve + UTF-8 check + lock (same as `init').
  2. Read FILE's current bytes; hash; store as `bases/<hex>'.
  3. Refresh `state.last_known_sha' (or create state.json if this is
     effectively a fresh init -- `open' auto-inits if no state.json
     exists yet, for ergonomics).
  4. Return `base_sha' + `base_path' + the conflict flag.

Note: `open' DOES NOT clear or modify `pending_conflict'. If the file
is in a conflicted state, `open' still succeeds (so a viewer can load
the marker-laden content into their buffer), but it sets
`conflicted: true' in the response and includes `pending_conflict'
metadata so the caller knows.

Spec refs: kb/spec/algorithms.md#open, kb/spec/protocols.md
Properties enforced: P5 (byte-exact), P6 (locked), P15 (base_path
hashes to base_sha).
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
    """Capture a fresh base snapshot. Auto-inits the sidecar if absent.

    The auto-init path (no state.json yet) is a usability concession:
    a caller that just did `cotype init' and then `cotype open' would
    otherwise have to wait between the two for some "ok the sidecar
    is ready" signal. We make `open' do the right thing on a
    sidecar-less file too.

    Returns the JSON envelope:
        {"status": "ok", "file": ..., "base_sha": "sha256:...",
         "base_path": "...",  "conflicted": bool,
         ["pending_conflict": {"id": ..., "path": ...}]}
    """
    file = resolve_target(file_arg)
    sidecar = sidecar_dir(file)
    ensure_layout(sidecar)  # auto-init: idempotent dir creation
    with sidecar_lock(sidecar):
        try:
            content = file.read_bytes()
        except OSError as e:
            raise IoError(f"reading {file}: {e}") from e
        # Open enforces UTF-8 too. Reasoning: any subsequent `cotype
        # save' would reject non-UTF-8 anyway, and storing a base of
        # unsupported bytes silently lets the caller think they're
        # in a managed state when they aren't.
        try:
            content.decode("utf-8")
        except UnicodeDecodeError as e:
            raise InvalidUtf8(f"{file} is not valid UTF-8") from e
        sha = hash_bytes(content)
        # `bp' is the path to the freshly-stored base. The CALLER
        # reads its working content from this path, not from FILE
        # itself -- see the "race-free read pattern" section in the
        # module docstring.
        bp = store_base(sidecar, content, sha)
        if state_exists(sidecar):
            # Refresh `last_known_sha' to the bytes we just captured.
            # Crucially, we DON'T clear `pending_conflict' here -- a
            # conflict survives any number of `open' calls until
            # `cotype resolve' clears it.
            st = read_state(sidecar)
            st.last_known_sha = sha
            st.target_path = relpath_from_sidecar(file, sidecar)
        else:
            # Auto-init path: no state.json yet, build one.
            st = State(
                target_path=relpath_from_sidecar(file, sidecar),
                last_known_sha=sha,
            )
        write_state(sidecar, st)
        # Include conflict metadata if a conflict is pending. The
        # response shape is documented at
        # kb/spec/api-contracts.md#cotype-open.
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
