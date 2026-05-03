"""Tests for stile.commands.init."""
from __future__ import annotations

from pathlib import Path

import pytest

from stile.commands.init import cmd_init
from stile.errors import InvalidUtf8, UnsupportedFile


def test_T1_P11_init_idempotence(tmp_path: Path):
    f = tmp_path / "file.txt"
    f.write_text("content\n")
    r1 = cmd_init(str(f))
    r2 = cmd_init(str(f))
    assert r1["sha"] == r2["sha"]
    sidecar = tmp_path / ".file.txt.stile"
    assert sidecar.is_dir()
    assert (sidecar / "state.json").exists()
    assert (sidecar / "bases").is_dir()
    assert (sidecar / "conflicts").is_dir()
    assert (sidecar / "tmp").is_dir()


def test_init_rejects_missing_target(tmp_path: Path):
    with pytest.raises(UnsupportedFile):
        cmd_init(str(tmp_path / "no.txt"))


def test_init_rejects_invalid_utf8(tmp_path: Path):
    f = tmp_path / "binary.bin"
    f.write_bytes(b"\xff\xfe\xfd")
    with pytest.raises(InvalidUtf8):
        cmd_init(str(f))


def test_init_returns_documented_payload(tmp_path: Path):
    f = tmp_path / "f.txt"
    f.write_text("x")
    r = cmd_init(str(f))
    assert r["status"] == "ok"
    assert r["file"] == str(f)
    assert r["sha"].startswith("sha256:")
    assert r["sidecar"].endswith(".f.txt.stile")
