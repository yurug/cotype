"""Tests for stile.commands.save -- conflict path and post-conflict gate."""
from __future__ import annotations

import json
from pathlib import Path

import pytest

from stile.commands.init import cmd_init
from stile.commands.open_ import cmd_open
from stile.commands.save import cmd_save
from stile.errors import ConflictPending


def test_T6_P4_stale_conflicting_save_writes_artifacts(tmp_path: Path):
    f = tmp_path / "f.txt"
    f.write_text("x\ny\nz\n")
    cmd_init(str(f))
    op = cmd_open(str(f))
    base_sha = op["base_sha"]

    # Conflicting overlapping edits on line 2.
    f.write_text("x\ny-current\nz\n")
    current_bytes = f.read_bytes()
    proposed = b"x\ny-proposed\nz\n"

    r = cmd_save(str(f), base_sha, "editor", proposed)
    assert r["status"] == "conflict"
    # P4(a): FILE byte-for-byte = current.
    assert f.read_bytes() == current_bytes
    # P4(c): all four artefacts present.
    cdir = Path(r["conflict_path"])
    assert (cdir / "base").read_bytes() == b"x\ny\nz\n"
    assert (cdir / "current").read_bytes() == current_bytes
    assert (cdir / "proposed").read_bytes() == proposed
    assert (cdir / "merged").exists()
    # meta.json has the documented shape.
    meta = json.loads((cdir / "meta.json").read_text())
    assert meta["id"] == r["conflict_id"]
    assert meta["actor"] == "editor"
    assert meta["base_sha"] == base_sha
    assert meta["current_sha"] == r["current_sha"]
    assert meta["proposed_sha"] == r["proposed_sha"]
    assert meta["created_at"].endswith("Z")


def test_T7_P7_pending_conflict_blocks_save(with_pending_conflict):
    f, cid = with_pending_conflict
    op = cmd_open(str(f))  # open is allowed even with a pending conflict
    with pytest.raises(ConflictPending):
        cmd_save(str(f), op["base_sha"], "test", b"anything\n")
    # FILE remains the "current" from the conflict.
    assert f.read_text() == "hello\nCURRENT\n"
