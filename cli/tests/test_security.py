"""Security-flavoured tests: tool-error vs conflict, path traversal, shell-meta actor."""
from __future__ import annotations

from pathlib import Path

import pytest

from stile.commands.init import cmd_init
from stile.commands.open_ import cmd_open
from stile.commands.save import cmd_save
from stile.errors import MergeToolError


def test_T20_P10_diff3_missing_is_tool_error_not_conflict(
    tmp_path: Path, monkeypatch
):
    f = tmp_path / "f.txt"
    f.write_text("a\nb\nc\n")
    cmd_init(str(f))
    op = cmd_open(str(f))
    base_sha = op["base_sha"]
    f.write_text("a\nB\nc\n")  # current differs from base
    monkeypatch.setenv("PATH", "")
    with pytest.raises(MergeToolError):
        cmd_save(str(f), base_sha, "test", b"a\nb-proposed\nc\n")
    # P10: FILE unchanged; no conflict directory created.
    assert f.read_bytes() == b"a\nB\nc\n"
    sidecar = tmp_path / ".f.txt.stile"
    assert list((sidecar / "conflicts").iterdir()) == []


def test_T19_actor_with_shell_metacharacters_is_safe(tmp_path: Path):
    """Actor strings are stored verbatim; never run through a shell."""
    f = tmp_path / "f.txt"
    f.write_text("x\n")
    cmd_init(str(f))
    op = cmd_open(str(f))
    # If this string ever reached a shell, $HOME would be expanded and `rm`
    # would run. We just check that save completes with mode=direct.
    r = cmd_save(
        str(f), op["base_sha"], "rm -rf $HOME && echo pwned", b"y\n"
    )
    assert r["mode"] == "direct"
    assert f.read_bytes() == b"y\n"
