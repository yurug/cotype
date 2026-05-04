"""Tests for cotype.commands.status."""
from __future__ import annotations

from pathlib import Path

from cotype.commands.init import cmd_init
from cotype.commands.status import cmd_status


def test_status_unmanaged(tmp_path: Path):
    f = tmp_path / "f.txt"
    f.write_text("x")
    r = cmd_status(str(f))
    assert r["status"] == "unmanaged"


def test_status_clean(tmp_path: Path):
    f = tmp_path / "f.txt"
    f.write_text("x")
    cmd_init(str(f))
    r = cmd_status(str(f))
    assert r["status"] == "clean"
    assert r["current_sha"].startswith("sha256:")
    assert r["last_known_sha"] == r["current_sha"]


def test_status_conflicted(with_pending_conflict):
    f, cid = with_pending_conflict
    r = cmd_status(str(f))
    assert r["status"] == "conflicted"
    assert r["pending_conflict"]["id"] == cid
