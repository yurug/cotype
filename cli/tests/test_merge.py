"""Tests for stile.merge -- the diff3 wrapper."""
from __future__ import annotations

from pathlib import Path

import pytest

from stile.errors import MergeToolError
from stile.merge import Clean, Conflict, merge3
from stile.store import ensure_layout


@pytest.fixture
def sidecar(tmp_path: Path) -> Path:
    s = tmp_path / ".f.stile"
    ensure_layout(s)
    return s


def test_merge3_clean_disjoint_edits(sidecar: Path):
    # Edits must be separated by >= 1 unchanged line for diff3 to treat the
    # regions as independent (see kb/external/diff3.md "Adjacency").
    base = b"a\nb\nc\nd\ne\n"
    current = b"a\nB\nc\nd\ne\n"
    proposed = b"a\nb\nc\nd\nE\n"
    r = merge3(base, current, proposed, sidecar)
    assert isinstance(r, Clean)
    assert b"B" in r.merged
    assert b"E" in r.merged


def test_merge3_adjacent_edits_treated_as_conflict(sidecar: Path):
    # SPEC §8 only says SHOULD return Clean for non-overlapping; diff3 treats
    # adjacent line edits as one contiguous region. Documented behaviour.
    base = b"x\ny\nz\n"
    current = b"x\ny1\nz\n"
    proposed = b"x\ny\nz1\n"
    r = merge3(base, current, proposed, sidecar)
    assert isinstance(r, Conflict)


def test_merge3_conflict_overlapping_edits(sidecar: Path):
    base = b"x\ny\nz\n"
    current = b"x\ny-current\nz\n"
    proposed = b"x\ny-proposed\nz\n"
    r = merge3(base, current, proposed, sidecar)
    assert isinstance(r, Conflict)
    # Conflict markers present.
    assert b"<<<<<<<" in r.merged_with_markers
    assert b"=======" in r.merged_with_markers
    assert b">>>>>>>" in r.merged_with_markers


def test_T20_P10_diff3_missing_is_tool_error(sidecar: Path, monkeypatch):
    # An empty PATH means diff3 cannot be located.
    monkeypatch.setenv("PATH", "")
    with pytest.raises(MergeToolError):
        merge3(b"a\n", b"b\n", b"c\n", sidecar)


def test_merge3_cleans_temp_files(sidecar: Path):
    merge3(b"a\nb\n", b"a\nb\n", b"a\nc\n", sidecar)
    leftovers = list((sidecar / "tmp").iterdir())
    assert leftovers == []
