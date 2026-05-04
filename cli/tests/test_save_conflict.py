"""Tests for cotype.commands.save -- conflict path and post-conflict gate."""
from __future__ import annotations

import json
from pathlib import Path

import pytest

from cotype.commands.init import cmd_init
from cotype.commands.open_ import cmd_open
from cotype.commands.save import cmd_save
from cotype.errors import ConflictPending


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
    # P4(a): FILE now contains the diff3 markers in place; both sides are
    # present so the user (or their editor) can resolve inline.
    file_bytes = f.read_bytes()
    assert b"<<<<<<< " in file_bytes
    assert b">>>>>>> " in file_bytes
    assert b"y-current" in file_bytes
    assert b"y-proposed" in file_bytes
    # P4(c): all four forensic artefacts still present in the sidecar.
    cdir = Path(r["conflict_path"])
    assert (cdir / "base").read_bytes() == b"x\ny\nz\n"
    assert (cdir / "current").read_bytes() == current_bytes
    assert (cdir / "proposed").read_bytes() == proposed
    assert (cdir / "merged").read_bytes() == file_bytes
    # meta.json has the documented shape.
    meta = json.loads((cdir / "meta.json").read_text())
    assert meta["id"] == r["conflict_id"]
    assert meta["actor"] == "editor"
    assert meta["base_sha"] == base_sha
    assert meta["current_sha"] == r["current_sha"]
    assert meta["proposed_sha"] == r["proposed_sha"]
    assert meta["created_at"].endswith("Z")


def test_T7_P7_pending_conflict_blocks_save(with_pending_conflict):
    f, _cid = with_pending_conflict
    before = f.read_bytes()
    op = cmd_open(str(f))  # open is allowed even with a pending conflict
    with pytest.raises(ConflictPending):
        cmd_save(str(f), op["base_sha"], "test", b"anything\n")
    # FILE remains in its conflicted state -- save is rejected without
    # touching it.
    assert f.read_bytes() == before
