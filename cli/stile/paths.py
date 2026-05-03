"""Filesystem path conventions: target file -> sidecar paths.

Spec refs: kb/spec/data-model.md#paths
Properties enforced: P-path-traversal-safety -- every path inside the sidecar
is constructed from a fixed scheme rooted at the sidecar dir; user-supplied
strings are validated before contributing to a path.
"""
from __future__ import annotations

import os
import re
import stat
from pathlib import Path

from stile.errors import UnsupportedFile

# Conflict ids are 32 lowercase hex chars (uuid4 hex with dashes stripped).
# This regex is the v0 contract; anything else is rejected before being used
# in a path -- closes the path-traversal vector through --conflict-id.
CONFLICT_ID_RE = re.compile(r"^[0-9a-f]{32}$")


def resolve_target(arg: str) -> Path:
    """Resolve `arg` to a real, absolute path. Reject non-regular files.

    Symlinks are followed (kb/spec/data-model.md#paths recommended policy).
    Two symlinks to the same underlying file therefore share one sidecar.
    """
    real = Path(os.path.realpath(arg))
    if not real.exists():
        raise UnsupportedFile(f"target {arg} does not exist")
    st = real.lstat()
    # inv: P-path-traversal-safety -- only regular files are managed
    if not stat.S_ISREG(st.st_mode):
        raise UnsupportedFile(f"target {arg} is not a regular file")
    return real


def sidecar_dir(file: Path) -> Path:
    """Return the sidecar dir for `file`: dirname/.basename.stile."""
    return file.parent / f".{file.name}.stile"


def base_path(sidecar: Path, hex_64: str) -> Path:
    """Path to the base snapshot identified by 64-char hex (no `sha256:` prefix)."""
    return sidecar / "bases" / hex_64


def conflict_dir(sidecar: Path, conflict_id: str) -> Path:
    """Path to a conflict directory. Validates `conflict_id` first.

    Raises ValueError on a malformed id. Callers (commands/) translate the
    ValueError to UsageError so the user-visible name stays stable.
    """
    if not CONFLICT_ID_RE.match(conflict_id):
        raise ValueError(f"bad conflict id: {conflict_id!r}")
    return sidecar / "conflicts" / conflict_id


def tmp_dir(sidecar: Path) -> Path:
    """Scratch dir for atomic writes and merge-input temp files."""
    return sidecar / "tmp"


def relpath_from_sidecar(file: Path, sidecar: Path) -> str:
    """Relative path from sidecar dir to FILE -- stored in state.json (informational)."""
    return os.path.relpath(file, start=sidecar)
