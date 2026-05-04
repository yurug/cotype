"""End-to-end test of examples/agent-loop using the deterministic mock agent.

Validates the headline use case: a file is edited by a user, an agent reads
the base, computes a reply, and cotype lands it. Subsequent passes with no
new user input become noops.
"""
from __future__ import annotations

import os
import subprocess
import sys
from pathlib import Path

# Test lives at <repo>/cli/tests/...; examples/ is at the monorepo root,
# three levels up from this file (parent x3).
REPO = Path(__file__).resolve().parent.parent.parent
DRIVER = REPO / "examples" / "agent-loop" / "run_agent.py"
MOCK = REPO / "examples" / "agent-loop" / "agent_mock.py"


def run_driver(file: Path) -> subprocess.CompletedProcess[bytes]:
    return subprocess.run(
        [sys.executable, str(DRIVER), str(file), "--agent", str(MOCK)],
        capture_output=True,
    )


def test_agent_loop_appends_reply_then_noops(tmp_path: Path):
    f = tmp_path / "task.md"
    f.write_text(
        "# Refactor the auth module\n\n## user\nWhat is brittle?\n",
        encoding="utf-8",
    )

    # First pass: agent appends a reply, save mode = direct.
    r = run_driver(f)
    assert r.returncode == 0, r.stderr
    out = f.read_text()
    assert "## agent (mock #1)" in out
    assert b"save: direct" in r.stderr or b"save: merged" in r.stderr

    # Second pass with no new user block: agent emits unchanged, mode = noop.
    snapshot = f.read_bytes()
    r = run_driver(f)
    assert r.returncode == 0, r.stderr
    assert f.read_bytes() == snapshot
    assert b"save: noop" in r.stderr


def test_agent_loop_handles_a_second_user_turn(tmp_path: Path):
    f = tmp_path / "task.md"
    f.write_text("# t\n\n## user\nQ1\n", encoding="utf-8")
    assert run_driver(f).returncode == 0
    assert "## agent (mock #1)" in f.read_text()

    # User adds another question.
    f.write_text(f.read_text() + "\n## user\nQ2\n", encoding="utf-8")
    r = run_driver(f)
    assert r.returncode == 0, r.stderr
    text = f.read_text()
    assert "## agent (mock #1)" in text
    assert "## agent (mock #2)" in text


def test_agent_loop_surfaces_conflict_with_exit_1(tmp_path: Path):
    """When the agent's base goes stale and edits collide, driver exits 1."""
    f = tmp_path / "task.md"
    # Set up so base = state at open, then mutate the file under the agent's
    # feet to force a stale base, with the agent's reply colliding with the
    # change. We achieve that by mutating EVERY line: the agent will append
    # at the end (no overlap there), but cotype will still see a stale base.
    # To force an actual conflict, the user's mutation must hit the same
    # region the agent's reply lands in.
    f.write_text("## user\nHello\n## agent (mock #0)\nold\n", encoding="utf-8")
    # Run once to register a base.
    subprocess.run(
        [sys.executable, "-m", "cotype", "init", str(f), "--json"], check=True
    )

    # Begin an "agent" pass: open captures base.
    open_proc = subprocess.run(
        [sys.executable, "-m", "cotype", "open", str(f), "--json"],
        check=True, capture_output=True,
    )
    import json as _json
    meta = _json.loads(open_proc.stdout)

    # Concurrent user edit on the LAST line (where mock would append).
    f.write_text("## user\nHello\n## agent (mock #0)\nUSER-EDITED\n", encoding="utf-8")

    # Now run the driver: it will open again (fresh base = the user's version),
    # the mock will see user_count=1, agent_count=1 -> emit unchanged ->
    # mode=noop. So the driver succeeds. To force the conflict we need to
    # save with the OLD base_sha. Use the CLI directly.
    proposed = b"## user\nHello\n## agent (mock #0)\nAGENT-WROTE-DIFFERENT\n"
    save = subprocess.run(
        [sys.executable, "-m", "cotype", "save", str(f),
         "--base-sha", meta["base_sha"], "--actor", "agent:test", "--json"],
        input=proposed, capture_output=True,
    )
    assert save.returncode == 1, save.stdout + save.stderr
    out = _json.loads(save.stdout)
    assert out["status"] == "conflict"

    # Now the driver itself must refuse to act while a conflict is pending.
    r = run_driver(f)
    assert r.returncode == 1
    assert b"conflict pending" in r.stderr
