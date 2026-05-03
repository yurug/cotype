"""CLI smoke tests via `python -m stile`."""
from __future__ import annotations

import json
import subprocess
import sys
from pathlib import Path


def run_cli(
    args: list[str], stdin: bytes = b""
) -> tuple[int, bytes, bytes]:
    proc = subprocess.run(
        [sys.executable, "-m", "stile", *args],
        input=stdin,
        capture_output=True,
    )
    return proc.returncode, proc.stdout, proc.stderr


def test_cli_help_exits_0():
    rc, out, _err = run_cli(["--help"])
    assert rc == 0
    assert b"init" in out
    assert b"save" in out
    assert b"resolve" in out


def test_cli_init_then_status_json(tmp_path: Path):
    f = tmp_path / "f.txt"
    f.write_text("hello\n")

    rc, out, err = run_cli(["init", str(f), "--json"])
    assert rc == 0, err
    obj = json.loads(out)
    assert obj["status"] == "ok"
    assert obj["sha"].startswith("sha256:")

    rc, out, err = run_cli(["status", str(f), "--json"])
    assert rc == 0, err
    obj = json.loads(out)
    assert obj["status"] == "clean"


def test_cli_save_direct_via_subprocess(tmp_path: Path):
    f = tmp_path / "f.txt"
    f.write_text("A\n")
    run_cli(["init", str(f), "--json"])
    rc, out, _ = run_cli(["open", str(f), "--json"])
    assert rc == 0
    base_sha = json.loads(out)["base_sha"]

    rc, out, err = run_cli(
        ["save", str(f), "--base-sha", base_sha, "--json"], stdin=b"B\n"
    )
    assert rc == 0, err
    obj = json.loads(out)
    assert obj["mode"] == "direct"
    assert f.read_text() == "B\n"


def test_cli_catbase_writes_bytes_to_stdout(tmp_path: Path):
    f = tmp_path / "f.txt"
    f.write_bytes(b"raw bytes here\n")
    run_cli(["init", str(f), "--json"])
    rc, out, err = run_cli(["cat-base", str(f)])
    assert rc == 0, err
    assert out == b"raw bytes here\n"


def test_cli_catbase_unknown_base_exits_4(tmp_path: Path):
    f = tmp_path / "f.txt"
    f.write_text("x\n")
    run_cli(["init", str(f), "--json"])
    rc, _out, err = run_cli(
        ["cat-base", str(f), "--base-sha", "sha256:" + "0" * 64]
    )
    assert rc == 4
    assert b"UnknownBase" in err


def test_cli_unknown_base_exits_4(tmp_path: Path):
    f = tmp_path / "f.txt"
    f.write_text("A\n")
    run_cli(["init", str(f), "--json"])
    rc, out, _ = run_cli(
        ["save", str(f), "--base-sha", "sha256:" + "0" * 64, "--json"],
        stdin=b"B\n",
    )
    assert rc == 4
    obj = json.loads(out)
    assert obj["status"] == "error"
    assert obj["error"] == "UnknownBase"


def test_cli_resolve_traversal_id_rejected(tmp_path: Path):
    f = tmp_path / "f.txt"
    f.write_text("x\ny\nz\n")
    run_cli(["init", str(f), "--json"])
    rc, out, _ = run_cli(["open", str(f), "--json"])
    base_sha = json.loads(out)["base_sha"]
    f.write_text("x\ny-current\nz\n")
    run_cli(
        ["save", str(f), "--base-sha", base_sha, "--json"],
        stdin=b"x\ny-proposed\nz\n",
    )
    rc, out, _ = run_cli(
        ["resolve", str(f), "--conflict-id", "../escape", "--json"],
        stdin=b"hi\n",
    )
    assert rc == 2
    assert json.loads(out)["error"] == "UsageError"


def test_cli_conflict_exits_1(tmp_path: Path):
    f = tmp_path / "f.txt"
    f.write_text("x\ny\nz\n")
    run_cli(["init", str(f), "--json"])
    rc, out, _ = run_cli(["open", str(f), "--json"])
    base_sha = json.loads(out)["base_sha"]
    f.write_text("x\ny-current\nz\n")
    rc, out, _ = run_cli(
        ["save", str(f), "--base-sha", base_sha, "--json"],
        stdin=b"x\ny-proposed\nz\n",
    )
    assert rc == 1
    obj = json.loads(out)
    assert obj["status"] == "conflict"
    assert "conflict_id" in obj
