"""Shared pytest fixtures for cotype tests."""
from __future__ import annotations

from pathlib import Path

import pytest

from cotype.commands.init import cmd_init
from cotype.commands.open_ import cmd_open
from cotype.commands.save import cmd_save


@pytest.fixture
def text_file(tmp_path: Path) -> Path:
    """A regular text file with simple content, NOT yet managed by cotype."""
    p = tmp_path / "file.txt"
    p.write_text("hello\nworld\n", encoding="utf-8")
    return p


@pytest.fixture
def managed(text_file: Path) -> Path:
    """A managed text file (post-init). Returns the path."""
    cmd_init(str(text_file))
    return text_file


@pytest.fixture
def with_pending_conflict(managed: Path) -> tuple[Path, str]:
    """Trigger T6: a stale conflicting save. Returns (path, conflict_id)."""
    op = cmd_open(str(managed))
    base_sha = op["base_sha"]
    # Another actor mutates FILE between open and save.
    managed.write_text("hello\nCURRENT\n", encoding="utf-8")
    proposed = b"hello\nPROPOSED\n"
    result = cmd_save(str(managed), base_sha, "test", proposed)
    assert result["status"] == "conflict", result
    return managed, result["conflict_id"]
