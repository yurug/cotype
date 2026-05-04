"""Tests for cotype.commands.save -- direct, noop, and reject paths."""
from __future__ import annotations

from pathlib import Path

import pytest

from cotype.commands.init import cmd_init
from cotype.commands.open_ import cmd_open
from cotype.commands.save import cmd_save
from cotype.errors import UnknownBase, UnmanagedFile
from cotype.hash import hash_bytes


def test_T3_P12_direct_save(tmp_path: Path):
    f = tmp_path / "f.txt"
    f.write_text("A\n")
    cmd_init(str(f))
    op = cmd_open(str(f))
    proposed = b"B\n"
    r = cmd_save(str(f), op["base_sha"], "test", proposed)
    assert r["status"] == "saved"
    assert r["mode"] == "direct"
    assert f.read_bytes() == proposed
    assert r["sha"] == hash_bytes(proposed)


def test_T4_P14_noop_save(tmp_path: Path):
    f = tmp_path / "f.txt"
    f.write_text("B\n")
    cmd_init(str(f))
    op = cmd_open(str(f))
    # current == proposed -> noop, regardless of base.
    r = cmd_save(str(f), op["base_sha"], "test", b"B\n")
    assert r["mode"] == "noop"
    assert f.read_bytes() == b"B\n"


def test_T9_P8_unknown_base_rejected(tmp_path: Path):
    f = tmp_path / "f.txt"
    f.write_text("A\n")
    cmd_init(str(f))
    fake_sha = "sha256:" + "0" * 64  # syntactically valid; not present.
    with pytest.raises(UnknownBase):
        cmd_save(str(f), fake_sha, "test", b"B\n")
    assert f.read_bytes() == b"A\n"


def test_T9_malformed_base_sha_rejected_as_unknown_base(tmp_path: Path):
    f = tmp_path / "f.txt"
    f.write_text("A\n")
    cmd_init(str(f))
    with pytest.raises(UnknownBase):
        cmd_save(str(f), "not-a-hash", "test", b"B\n")


def test_save_unmanaged_file(tmp_path: Path):
    f = tmp_path / "f.txt"
    f.write_text("A\n")
    with pytest.raises(UnmanagedFile):
        cmd_save(str(f), "sha256:" + "0" * 64, "test", b"B\n")
