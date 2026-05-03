"""Tests for stile.commands.resolve."""
from __future__ import annotations

from pathlib import Path

import pytest

from stile.commands.init import cmd_init
from stile.commands.resolve import cmd_resolve
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
