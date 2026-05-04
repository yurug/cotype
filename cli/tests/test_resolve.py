"""Tests for stile.commands.resolve."""
from __future__ import annotations

from pathlib import Path

import pytest

from stile.commands.init import cmd_init
from stile.commands.resolve import _has_conflict_markers, cmd_resolve
from stile.commands.save import cmd_save
from stile.commands.open_ import cmd_open
from stile.commands.status import cmd_status
from stile.errors import ConflictPending, UsageError


def test_T8_resolve_clears_conflict(with_pending_conflict):
    """User edits FILE to remove markers; `stile resolve FILE` accepts."""
    f, _cid = with_pending_conflict
    # The user opens FILE in their editor and removes the markers.
    f.write_bytes(b"hello\nresolved\n")
    r = cmd_resolve(str(f), "user")
    assert r["status"] == "resolved"
    assert f.read_bytes() == b"hello\nresolved\n"
    assert cmd_status(str(f))["status"] == "clean"


def test_resolve_refuses_when_markers_remain(with_pending_conflict):
    """If the user runs resolve before removing markers, refuse."""
    f, _cid = with_pending_conflict
    before = f.read_bytes()
    assert _has_conflict_markers(before), "fixture should leave markers in FILE"
    with pytest.raises(UsageError, match="conflict markers"):
        cmd_resolve(str(f))
    # FILE unchanged; conflict still pending.
    assert f.read_bytes() == before
    assert cmd_status(str(f))["status"] == "conflicted"


def test_resolve_rejects_when_no_pending(tmp_path: Path):
    f = tmp_path / "f.txt"
    f.write_text("x")
    cmd_init(str(f))
    with pytest.raises(UsageError, match="no pending conflict"):
        cmd_resolve(str(f))


def test_resolve_then_save_works_again(with_pending_conflict):
    """After resolve, an ordinary save proceeds (no more ConflictPending)."""
    f, _ = with_pending_conflict
    f.write_bytes(b"hello\nresolved\n")
    cmd_resolve(str(f))
    op = cmd_open(str(f))
    r = cmd_save(str(f), op["base_sha"], "user", b"hello\nupdated\n")
    assert r["status"] == "saved" and r["mode"] == "direct"
    assert f.read_bytes() == b"hello\nupdated\n"


def test_save_after_conflict_still_blocked_until_resolve(with_pending_conflict):
    """ConflictPending is enforced even if the user edits FILE without resolving."""
    f, _ = with_pending_conflict
    # User edits markers out but forgets to run `stile resolve`.
    f.write_bytes(b"hello\nresolved\n")
    op = cmd_open(str(f))
    with pytest.raises(ConflictPending):
        cmd_save(str(f), op["base_sha"], "test", b"anything\n")


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
