"""Tests for stile.store."""
from __future__ import annotations

import json
from pathlib import Path

import pytest

from stile.errors import CorruptSidecar
from stile.hash import hash_bytes
from stile.store import (
    State,
    ensure_layout,
    read_state,
    state_exists,
    store_base,
    write_state,
)


def test_state_roundtrip(tmp_path: Path):
    sidecar = tmp_path / ".f.stile"
    ensure_layout(sidecar)
    st = State(target_path="../f", last_known_sha="sha256:" + "a" * 64)
    write_state(sidecar, st)
    got = read_state(sidecar)
    assert got.target_path == "../f"
    assert got.last_known_sha == "sha256:" + "a" * 64
    assert got.pending_conflict is None
    assert got.format_version == 1


def test_state_rejects_unsupported_format_version(tmp_path: Path):
    sidecar = tmp_path / ".f.stile"
    ensure_layout(sidecar)
    (sidecar / "state.json").write_text(
        json.dumps(
            {"format_version": 99, "target_path": "x", "last_known_sha": "y"}
        )
    )
    with pytest.raises(CorruptSidecar):
        read_state(sidecar)


def test_T15_corrupt_state_json_rejected(tmp_path: Path):
    sidecar = tmp_path / ".f.stile"
    ensure_layout(sidecar)
    (sidecar / "state.json").write_text("{not json")
    with pytest.raises(CorruptSidecar):
        read_state(sidecar)


def test_state_rejects_missing_required_fields(tmp_path: Path):
    sidecar = tmp_path / ".f.stile"
    ensure_layout(sidecar)
    (sidecar / "state.json").write_text(json.dumps({"format_version": 1}))
    with pytest.raises(CorruptSidecar):
        read_state(sidecar)


def test_store_base_dedupes(tmp_path: Path):
    sidecar = tmp_path / ".f.stile"
    ensure_layout(sidecar)
    content = b"hello\n"
    sha = hash_bytes(content)
    p1 = store_base(sidecar, content, sha)
    p2 = store_base(sidecar, content, sha)
    assert p1 == p2
    assert p1.read_bytes() == content


def test_state_exists_negative(tmp_path: Path):
    sidecar = tmp_path / ".f.stile"
    sidecar.mkdir()
    assert state_exists(sidecar) is False
