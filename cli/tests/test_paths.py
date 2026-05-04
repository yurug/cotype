"""Tests for cotype.paths."""
from __future__ import annotations

from pathlib import Path

import pytest

from cotype.errors import UnsupportedFile
from cotype.paths import (
    CONFLICT_ID_RE,
    base_path,
    conflict_dir,
    resolve_target,
    sidecar_dir,
)


def test_sidecar_dir_naming(tmp_path: Path):
    f = tmp_path / "todo.txt"
    f.write_text("x")
    assert sidecar_dir(f) == tmp_path / ".todo.txt.cotype"


def test_resolve_target_rejects_missing(tmp_path: Path):
    with pytest.raises(UnsupportedFile):
        resolve_target(str(tmp_path / "missing.txt"))


def test_resolve_target_rejects_dir(tmp_path: Path):
    with pytest.raises(UnsupportedFile):
        resolve_target(str(tmp_path))


def test_T17_resolve_symlink_to_real_path(tmp_path: Path):
    real = tmp_path / "real.txt"
    real.write_text("ok")
    link = tmp_path / "link.txt"
    link.symlink_to(real)
    out = resolve_target(str(link))
    assert out == real.resolve()


def test_T18_relative_and_absolute_paths_match(tmp_path: Path, monkeypatch):
    f = tmp_path / "a.txt"
    f.write_text("x")
    monkeypatch.chdir(tmp_path)
    a = resolve_target("a.txt")
    b = resolve_target(str(f))
    assert a == b


def test_conflict_id_regex_only_accepts_32_lower_hex():
    assert CONFLICT_ID_RE.match("a" * 32)
    assert CONFLICT_ID_RE.match("0123456789abcdef0123456789abcdef")
    # Reject anything that could escape the conflicts/ directory.
    assert not CONFLICT_ID_RE.match("..")
    assert not CONFLICT_ID_RE.match("../escape")
    assert not CONFLICT_ID_RE.match("A" * 32)  # uppercase
    assert not CONFLICT_ID_RE.match("a" * 31)  # too short
    assert not CONFLICT_ID_RE.match("a" * 33)  # too long
    assert not CONFLICT_ID_RE.match("g" * 32)  # non-hex


def test_conflict_dir_rejects_bad_id(tmp_path: Path):
    with pytest.raises(ValueError):
        conflict_dir(tmp_path, "../escape")


def test_base_path_layout(tmp_path: Path):
    sidecar = tmp_path / ".x.cotype"
    p = base_path(sidecar, "a" * 64)
    assert p == sidecar / "bases" / ("a" * 64)
