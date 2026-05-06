"""`cotype init FILE` -- create the sidecar and capture the first base.

What `init' does, in order:

  1. Resolve `file_arg' to a real path (`paths.resolve_target' --
     refuses non-regular files).
  2. Compute the sidecar dir next to it.
  3. Ensure the sidecar's directory layout exists (idempotent).
  4. Take the sidecar lock.
  5. Read FILE's bytes.
  6. Validate UTF-8 (cotype manages UTF-8 only).
  7. Hash the bytes; store as `bases/<hex>'.
  8. Write/refresh state.json with `last_known_sha = <new sha>'.

Idempotence (P11) is the property worth thinking about: running
`cotype init FILE' twice in a row is a no-op the second time, modulo
refreshing the recorded `target_path'. We never destroy a prior
state.json or pending_conflict here -- if the file is already
managed, we just ensure the latest content is captured as a base.

Why we re-store the base on every init (even when sidecar already
exists): the file's content might have changed BETWEEN the original
init and this one (maybe someone wrote to FILE directly, ignoring the
protocol). Re-storing means subsequent `cotype open' requests can find
the latest content as a base. Doing nothing on the re-init path would
leave `last_known_sha' stale relative to disk, surprising the next
caller.

What `init' does NOT do:

  - It does not clear `pending_conflict'. If you `init' a file that's
    in a conflicted state, the conflict survives -- the user still
    needs to resolve.
  - It does not capture multiple bases or any history. Cotype is
    *not* a VCS in that sense; `init' is essentially "start managing
    this file from this point onward".

Spec refs: kb/spec/algorithms.md#init
Properties enforced: P11 (idempotent), P5 (byte-exact hash), P6 (locked).
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


def cmd_init(file_arg: str) -> dict:
    """Initialise the sidecar for `file_arg`. Idempotent.

    Returns the JSON envelope:
        {"status": "ok", "file": str(file), "sha": "sha256:...",
         "sidecar": str(sidecar)}
    """
    file = resolve_target(file_arg)
    sidecar = sidecar_dir(file)
    # `ensure_layout' creates `sidecar/`, `bases/`, `conflicts/`, and
    # `tmp/` if missing. Idempotent on every call after the first.
    ensure_layout(sidecar)
    with sidecar_lock(sidecar):
        try:
            content = file.read_bytes()
        except OSError as e:
            raise IoError(f"reading {file}: {e}") from e
        # Refuse non-UTF-8 up-front. Doing this AFTER taking the lock
        # is intentional: the lock guarantees no concurrent writer
        # changes the bytes between the read and this validation.
        try:
            content.decode("utf-8")
        except UnicodeDecodeError as e:
            raise InvalidUtf8(f"{file} is not valid UTF-8") from e
        sha = hash_bytes(content)
        # Storing the base is idempotent on identical content (see
        # `store_base'); on the re-init path we just re-confirm the
        # base file exists with the right hash, which is cheap.
        store_base(sidecar, content, sha)
        if state_exists(sidecar):
            # Idempotent path: validate the existing state.json shape
            # (via `read_state'), then refresh advisory fields.
            # We deliberately do NOT clear `pending_conflict' here --
            # `init' shouldn't be a way to silently drop pending
            # state.
            st = read_state(sidecar)
            st.last_known_sha = sha
            st.target_path = relpath_from_sidecar(file, sidecar)
        else:
            # First init: build a fresh State from scratch.
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
