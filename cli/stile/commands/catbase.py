"""`stile cat-base FILE [--base-sha HASH]` -- write a base snapshot's bytes to stdout.

Spec refs: kb/spec/api-contracts.md (cat-base section)

This is the read-only counterpart of `open`. With no `--base-sha` it returns
the bytes of `state.last_known_sha`; with `--base-sha HASH` it returns the
bytes of the explicitly named base. Useful in shell pipelines that need the
"current base" content without going through `open` (which would also store
a new snapshot).

No lock is required: bases/<hex> files are content-addressed and immutable
once stored, and state.json is written via atomic-replace so any read sees
either the previous or the new version in full.
"""
from __future__ import annotations

from stile.errors import IoError, UnknownBase, UnmanagedFile
from stile.hash import hex_part
from stile.paths import base_path, resolve_target, sidecar_dir
from stile.store import read_state, state_exists


def cmd_catbase(file_arg: str, base_sha: str | None) -> bytes:
    """Return the bytes of a base snapshot.

    Args:
        file_arg:  path to the managed file.
        base_sha:  the base to read. If None, defaults to state.last_known_sha.

    Raises:
        UnmanagedFile: sidecar absent.
        UnknownBase:   `base_sha` is malformed or no bases/<hex> file exists.
        IoError:       OS error while reading the base.
    """
    file = resolve_target(file_arg)
    sidecar = sidecar_dir(file)
    if not state_exists(sidecar):
        raise UnmanagedFile(f"{file} is not managed by stile")

    if base_sha is None:
        st = read_state(sidecar)
        base_sha = st.last_known_sha
    hex_64 = hex_part(base_sha)  # also raises UnknownBase on bad form
    bp = base_path(sidecar, hex_64)
    if not bp.exists():
        raise UnknownBase(f"base snapshot {base_sha} is not present")
    try:
        return bp.read_bytes()
    except OSError as e:
        raise IoError(f"reading base {bp}: {e}") from e
