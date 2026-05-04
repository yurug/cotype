"""Tests for cotype.commands.catbase."""
from __future__ import annotations

from pathlib import Path

import pytest

from cotype.commands.catbase import cmd_catbase
from cotype.commands.init import cmd_init
from cotype.commands.open_ import cmd_open
from cotype.commands.save import cmd_save
from cotype.errors import UnknownBase, UnmanagedFile


def test_catbase_returns_explicit_base_bytes(tmp_path: Path):
    f = tmp_path / "f.txt"
    f.write_text("hello world\n")
    cmd_init(str(f))
    op = cmd_open(str(f))
    assert cmd_catbase(str(f), op["base_sha"]) == b"hello world\n"


def test_catbase_default_uses_last_known_sha(tmp_path: Path):
    f = tmp_path / "f.txt"
    f.write_text("first content\n")
    cmd_init(str(f))
    assert cmd_catbase(str(f), None) == b"first content\n"


def test_catbase_tracks_last_known_after_save(tmp_path: Path):
    f = tmp_path / "f.txt"
    f.write_text("v1\n")
    cmd_init(str(f))
    op = cmd_open(str(f))
    cmd_save(str(f), op["base_sha"], "test", b"v2\n")
    # state.last_known_sha now points to v2; cat-base default reflects that.
    assert cmd_catbase(str(f), None) == b"v2\n"


def test_catbase_unknown_base_rejected(tmp_path: Path):
    f = tmp_path / "f.txt"
    f.write_text("x\n")
    cmd_init(str(f))
    with pytest.raises(UnknownBase):
        cmd_catbase(str(f), "sha256:" + "0" * 64)


def test_catbase_malformed_sha_rejected(tmp_path: Path):
    f = tmp_path / "f.txt"
    f.write_text("x\n")
    cmd_init(str(f))
    with pytest.raises(UnknownBase):
        cmd_catbase(str(f), "not-a-hash")


def test_catbase_unmanaged(tmp_path: Path):
    f = tmp_path / "f.txt"
    f.write_text("x\n")
    with pytest.raises(UnmanagedFile):
        cmd_catbase(str(f), None)
