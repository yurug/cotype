"""Tests for stile.commands.resolve."""
from __future__ import annotations

from pathlib import Path

import pytest

from stile.commands.init import cmd_init
from stile.commands.resolve import cmd_resolve, _has_conflict_markers
from stile.commands.status import cmd_status
from stile.errors import ConflictIdMismatch, UsageError


def test_T8_resolve_clears_conflict(with_pending_conflict):
    f, cid = with_pending_conflict
    r = cmd_resolve(str(f), cid, "user", b"resolved\n")
    assert r["status"] == "resolved"
    assert f.read_bytes() == b"resolved\n"
    s = cmd_status(str(f))
    assert s["status"] == "clean"


def test_resolve_rejects_id_mismatch(with_pending_conflict):
    f, _cid = with_pending_conflict
    with pytest.raises(ConflictIdMismatch):
        cmd_resolve(str(f), "1" * 32, "user", b"resolved\n")


def test_resolve_rejects_when_no_pending(tmp_path: Path):
    f = tmp_path / "f.txt"
    f.write_text("x")
    cmd_init(str(f))
    with pytest.raises(UsageError):
        cmd_resolve(str(f), "a" * 32, "user", b"x")


# --- --use-merged shortcut --------------------------------------------------


def _merged_path(f: Path, cid: str) -> Path:
    """Locate <sidecar>/conflicts/<cid>/merged for a managed file."""
    return f.parent / f".{f.name}.stile" / "conflicts" / cid / "merged"


def test_resolve_use_merged_happy_path(with_pending_conflict):
    f, cid = with_pending_conflict
    # Edit the merged file to remove markers (simulate what a user does).
    _merged_path(f, cid).write_bytes(b"hand-edited resolution\n")
    r = cmd_resolve(str(f), use_merged=True, actor="user")
    assert r["status"] == "resolved"
    assert f.read_bytes() == b"hand-edited resolution\n"
    assert cmd_status(str(f))["status"] == "clean"


def test_resolve_use_merged_refuses_with_markers(with_pending_conflict):
    f, cid = with_pending_conflict
    # Don't edit -- the merged file from diff3 still has <<<<<<< / >>>>>>>.
    before = f.read_bytes()
    with pytest.raises(UsageError, match="conflict markers"):
        cmd_resolve(str(f), use_merged=True)
    # FILE unchanged; conflict still pending.
    assert f.read_bytes() == before
    assert cmd_status(str(f))["status"] == "conflicted"


def test_resolve_use_merged_combined_with_explicit_args_rejected(
    with_pending_conflict,
):
    f, cid = with_pending_conflict
    with pytest.raises(UsageError, match="cannot be combined"):
        cmd_resolve(str(f), conflict_id=cid, use_merged=True, resolved=b"x\n")


def test_resolve_use_merged_no_pending(tmp_path: Path):
    f = tmp_path / "f.txt"
    f.write_text("x")
    cmd_init(str(f))
    with pytest.raises(UsageError, match="no pending conflict"):
        cmd_resolve(str(f), use_merged=True)


def test_has_conflict_markers_detects_full_block():
    body = (
        b"intro\n"
        b"<<<<<<< /tmp/x\nproposed\n"
        b"||||||| /tmp/b\nbase\n"
        b"=======\ncurrent\n"
        b">>>>>>> /tmp/y\noutro\n"
    )
    assert _has_conflict_markers(body) is True


def test_has_conflict_markers_ignores_lone_equals_underline():
    # Markdown Setext H1 underline: `=======` on a line by itself, no
    # accompanying <<<<<<< / >>>>>>> headers. Must NOT trigger.
    body = b"Title\n=======\n\nSome body text.\n"
    assert _has_conflict_markers(body) is False
