"""Tests for cotype.commands.save -- 3-way merge (compatible) path."""
from __future__ import annotations

from pathlib import Path

from cotype.commands.init import cmd_init
from cotype.commands.open_ import cmd_open
from cotype.commands.save import cmd_save


def test_T5_P1_stale_compatible_save_merges(tmp_path: Path):
    # T5 stale compatible save -- diff3 needs at least one unchanged line
    # between regions to treat the edits as disjoint (see kb/external/diff3.md).
    f = tmp_path / "f.txt"
    f.write_text("a\nb\nc\nd\ne\n")
    cmd_init(str(f))
    op = cmd_open(str(f))
    base_sha = op["base_sha"]

    # Another actor edits line 2.
    f.write_text("a\nB\nc\nd\ne\n")
    # Editor submits an edit to line 5.
    proposed = b"a\nb\nc\nd\nE\n"

    r = cmd_save(str(f), base_sha, "editor", proposed)
    assert r["status"] == "saved"
    assert r["mode"] == "merged"
    merged = f.read_bytes()
    # Both edits preserved.
    assert b"B" in merged
    assert b"E" in merged
