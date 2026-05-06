"""`cotype cat-base FILE [--base-sha HASH]' -- stream a base snapshot's bytes.

What it's for
=============

A read-only counterpart to `cotype open'. Returns the raw bytes of a
named base snapshot. Two usage modes:

    cotype cat-base FILE                    # last_known_sha
    cotype cat-base FILE --base-sha HASH    # explicit

Useful in shell pipelines that want to read the "current base" without
going through `cotype open' (which would create a new snapshot,
update `last_known_sha', and write state.json -- side effects you
might not want):

    # Run a generator on the current base, save the result.
    meta=$(cotype open FILE --json)
    base_sha=$(... | jq -r .base_sha)
    cotype cat-base FILE --base-sha "$base_sha" \\
        | my-generator                                 \\
        | cotype save FILE --base-sha "$base_sha" \\
            --actor agent:my-generator --json

Why no `--json` flag, why no lock
==================================

`cat-base' deliberately bypasses the JSON envelope: success is raw
bytes streamed to stdout. Mixing JSON metadata with the bytes payload
on the same stream would be unparseable. Errors take the standard
stderr path (`error: <Name>: <message>') with the right exit code.

No lock is required because:

  - `bases/<hex>' files are content-addressed (P5: hash IS identity)
    and IMMUTABLE once stored. We never overwrite or delete a base
    once it's there. So there's no read-while-write race to worry
    about.
  - When we DO need to read `last_known_sha' (for the no-arg path),
    that's one read of `state.json'. State.json is written via
    `atomic_replace', so a concurrent reader sees either the old
    or the new version in full -- never a torn write. Either is
    correct: we read whichever is current at the moment we look.

This is the only cotype subcommand that doesn't take a lock. The
property "every mutating command holds the sidecar lock" (P6) still
holds because `cat-base' isn't mutating.

Spec refs: kb/spec/api-contracts.md (cat-base section)
"""
from __future__ import annotations

from cotype.errors import IoError, UnknownBase, UnmanagedFile
from cotype.hash import hex_part
from cotype.paths import base_path, resolve_target, sidecar_dir
from cotype.store import read_state, state_exists


def cmd_catbase(file_arg: str, base_sha: str | None) -> bytes:
    """Return the bytes of a base snapshot.

    Args:
        file_arg:  path to the managed file.
        base_sha:  the base to read; if None, falls through to
                   state.last_known_sha (i.e., the most recently
                   captured base).

    Returns the raw bytes of the named base. The CLI layer
    (`cli.main') writes them to stdout verbatim.

    Raises:
        UnmanagedFile: sidecar absent.
        UnknownBase:   `base_sha' is malformed (bad form rejected by
                        `hex_part') OR no `bases/<hex>' file exists.
        IoError:       OS error while reading the base file.
    """
    file = resolve_target(file_arg)
    sidecar = sidecar_dir(file)
    if not state_exists(sidecar):
        raise UnmanagedFile(f"{file} is not managed by cotype")

    if base_sha is None:
        # No-arg path: read state.json to find the most recently
        # captured base. No lock needed -- state.json's own writes
        # are atomic.
        st = read_state(sidecar)
        base_sha = st.last_known_sha

    # Validate `base_sha' shape AND extract the hex suffix used as
    # filename. `hex_part' raises `UnknownBase' on malformed input,
    # which is the right user-facing error.
    hex_64 = hex_part(base_sha)
    bp = base_path(sidecar, hex_64)
    if not bp.exists():
        raise UnknownBase(f"base snapshot {base_sha} is not present")
    try:
        return bp.read_bytes()
    except OSError as e:
        raise IoError(f"reading base {bp}: {e}") from e
