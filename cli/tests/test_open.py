"""Tests for cotype.commands.open_."""
from __future__ import annotations

from pathlib import Path

from cotype.commands.init import cmd_init
from cotype.commands.open_ import cmd_open
from cotype.hash import hash_bytes


def test_T2_P15_open_returns_base_path_matching_base_sha(tmp_path: Path):
    f = tmp_path / "f.txt"
    f.write_text("hello\n")
    cmd_init(str(f))
    r = cmd_open(str(f))
    base_path = Path(r["base_path"])
    assert base_path.exists()
    assert hash_bytes(base_path.read_bytes()) == r["base_sha"]


def test_open_auto_inits_when_sidecar_absent(tmp_path: Path):
    f = tmp_path / "f.txt"
    f.write_text("hi\n")
    r = cmd_open(str(f))
    assert r["status"] == "ok"
    assert (tmp_path / ".f.txt.cotype" / "state.json").exists()


def test_open_reports_pending_conflict(with_pending_conflict):
    f, cid = with_pending_conflict
    r = cmd_open(str(f))
    assert r["conflicted"] is True
    assert r["pending_conflict"]["id"] == cid
