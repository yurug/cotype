"""Tests for stile.atomic_write."""
from __future__ import annotations

import stat
from pathlib import Path

from stile.atomic_write import atomic_replace
from stile.store import ensure_layout


def test_P12_atomic_replace_overwrites_content(tmp_path: Path):
    target = tmp_path / "file.txt"
    target.write_bytes(b"OLD")
    sidecar = tmp_path / ".file.txt.stile"
    ensure_layout(sidecar)
    atomic_replace(target, b"NEW CONTENT", sidecar)
    assert target.read_bytes() == b"NEW CONTENT"


def test_P12_atomic_replace_creates_target(tmp_path: Path):
    target = tmp_path / "new.txt"
    sidecar = tmp_path / ".new.txt.stile"
    ensure_layout(sidecar)
    atomic_replace(target, b"hello", sidecar)
    assert target.read_bytes() == b"hello"


def test_P13_mode_preserved_after_replace(tmp_path: Path):
    target = tmp_path / "secret.txt"
    target.write_bytes(b"hush")
    target.chmod(0o600)
    before = stat.S_IMODE(target.stat().st_mode)
    sidecar = tmp_path / ".secret.txt.stile"
    ensure_layout(sidecar)
    atomic_replace(target, b"updated", sidecar)
    after = stat.S_IMODE(target.stat().st_mode)
    assert before == 0o600
    assert after == 0o600


def test_atomic_replace_leaves_no_temp_files(tmp_path: Path):
    target = tmp_path / "f.txt"
    target.write_bytes(b"x")
    sidecar = tmp_path / ".f.txt.stile"
    ensure_layout(sidecar)
    atomic_replace(target, b"y", sidecar)
    # tmp dir should be empty after a successful replace.
    leftovers = list((sidecar / "tmp").iterdir())
    assert leftovers == []
