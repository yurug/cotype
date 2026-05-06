"""Filesystem path conventions -- where the sidecar lives and how its
internals are addressed.

The sidecar layout
==================

For a managed file at `dir/FILE`, cotype's per-file state lives at:

    dir/.FILE.cotype/
        lock           -- the exclusive flock target (lock.py)
        state.json     -- the small persistent state (store.py)
        bases/         -- one file per captured base snapshot,
                          named by its 64-char hex sha
        conflicts/     -- one directory per pending or past conflict,
                          named by its 32-char hex uuid (server-
                          generated; never accepted from a flag)
        tmp/           -- scratch space for atomic writes and merge
                          temp files; on the SAME filesystem as FILE
                          so `os.replace' is a true atomic rename

The "co-located beside FILE" choice is deliberate. Any other location
(home dir, /var, /tmp) would require the sidecar to point at FILE via
some external index; co-location means there's nothing to lose track
of. Move FILE, drag the sidecar with it. Delete the sidecar, the file
just becomes unmanaged again -- nothing else to clean up.

The naming convention `.<basename>.cotype` keeps the sidecar hidden
from `ls` (the leading dot) and visually associated with FILE (the
basename appears) without any chance of accidentally clashing with a
sibling file: `.<basename>.cotype` is a directory; FILE is a file;
the suffix makes the relationship obvious.

Path-traversal hardening
========================

P-path-traversal-safety: every path inside the sidecar is constructed
from a fixed scheme rooted at the sidecar dir. No user-supplied string
is concatenated into a filesystem path without validation. Concretely:

  - `bases/<hex>' uses `hex_part' (in hash.py) which enforces the
    `[0-9a-f]{64}' shape on the user's --base-sha BEFORE we touch the
    filesystem. A `--base-sha sha256:../escape' is rejected at the
    regex layer.
  - `conflicts/<id>' uses `CONFLICT_ID_RE' (here) which enforces 32
    lowercase hex chars. Conflict ids are generated server-side
    (`uuid.uuid4().hex') and never accepted from a CLI flag, but the
    validation runs anyway as defence in depth.
  - `target_path' in state.json is informational only -- never used
    as a path that gets written to or read from after init.

If a future feature needs to route a user string into a path component
(e.g., a `--actor name` that becomes a directory), it MUST go through
a validator like the ones above before touching disk.

Spec refs: kb/spec/data-model.md#paths
Properties enforced: P-path-traversal-safety
"""
from __future__ import annotations

import os
import re
import stat
from pathlib import Path

from cotype.errors import UnsupportedFile

# Conflict ids are 32 lowercase hex chars (uuid4 hex with dashes
# stripped). Server-generated; we still validate the value before
# composing it into a path, on the principle that "every byte that
# becomes a path component goes through a validator."
CONFLICT_ID_RE = re.compile(r"^[0-9a-f]{32}$")


def resolve_target(arg: str) -> Path:
    """Resolve `arg` to a real, absolute path -- and reject anything
    that isn't a regular file.

    Symlinks are followed (`os.path.realpath'): two symlinks pointing
    at the same underlying file therefore share one sidecar (because
    the sidecar is computed from the resolved path). That's the right
    behaviour -- editing FILE through a symlink is still editing FILE.

    Special files (directories, FIFOs, sockets, devices) are refused:
    the safe-save dance assumes `os.replace' semantics that don't hold
    for special files. A directory has no inode-swap analog; a FIFO
    has no "old contents"; a device's behaviour on rename-over is
    platform-defined. cotype declines to manage any of them.
    """
    real = Path(os.path.realpath(arg))
    if not real.exists():
        raise UnsupportedFile(f"target {arg} does not exist")
    st = real.lstat()
    if not stat.S_ISREG(st.st_mode):
        raise UnsupportedFile(f"target {arg} is not a regular file")
    return real


def sidecar_dir(file: Path) -> Path:
    """Return the sidecar dir for `file': dirname/.basename.cotype.

    Pure: doesn't check whether the dir exists. `state_exists' (in
    store.py) is the way to ask "is FILE managed?".
    """
    return file.parent / f".{file.name}.cotype"


def base_path(sidecar: Path, hex_64: str) -> Path:
    """Path to the base snapshot identified by `hex_64' (no `sha256:' prefix).

    Pure path composition. The caller is expected to have validated
    `hex_64' via `hash.hex_part' before getting here -- if you pass
    in a string with `..` components, this function will happily
    return a path that escapes the sidecar.
    """
    return sidecar / "bases" / hex_64


def conflict_dir(sidecar: Path, conflict_id: str) -> Path:
    """Path to a conflict directory. Validates `conflict_id` first.

    Defence in depth: even though conflict ids are generated
    server-side and aren't user-controllable today, this function
    validates anyway. Future code that routes any externally-derived
    id into a conflict_dir() call will get a `ValueError' instead of
    silently composing it into a path.

    The translation from `ValueError' here to `UsageError' for the
    user is done by the calling command (in `commands/`) so the wire
    contract stays uniform.
    """
    if not CONFLICT_ID_RE.match(conflict_id):
        raise ValueError(f"bad conflict id: {conflict_id!r}")
    return sidecar / "conflicts" / conflict_id


def tmp_dir(sidecar: Path) -> Path:
    """Scratch dir for atomic writes and merge-input temp files.

    Lives inside the sidecar so it's on the same filesystem as FILE;
    `os.replace' from `tmp_dir/foo' to FILE is then a true atomic
    rename (cross-fs `os.replace' is `EXDEV' on POSIX).
    """
    return sidecar / "tmp"


def relpath_from_sidecar(file: Path, sidecar: Path) -> str:
    """Relative path from sidecar dir to FILE -- stored in state.json.

    Informational only. We never *use* this path to read or write FILE
    (that path comes back through `resolve_target' on each command
    invocation). It's recorded so a human poking around inside the
    sidecar can tell at a glance which file it manages, even if the
    user has moved or renamed FILE since `init`.
    """
    return os.path.relpath(file, start=sidecar)
