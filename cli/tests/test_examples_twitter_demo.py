"""Regression tests for examples/twitter-demo.

Locks in BOTH demo flavours' direct/merged/merged outcome so a future
edit to the seed template, the agents, the barrier logic, or `stile
save`'s branching can't silently break the advertised story.
"""
from __future__ import annotations

import json
import os
import subprocess
import sys
import time
from pathlib import Path

REPO = Path(__file__).resolve().parent.parent.parent
DEMO = REPO / "examples" / "twitter-demo"
SETUP = DEMO / "setup.sh"
SETUP_CLAUDE = DEMO / "setup-claude.sh"
ORCH = DEMO / "orchestrate.py"
BG_AGENT = DEMO / "bg-agent.py"
BG_CLAUDE = DEMO / "bg-claude.py"

SEED_SLOTS = ("SLOT_REVIEWER", "SLOT_LINTER", "SLOT_TESTER")
EXPECTED_HEADINGS = (
    "## agent:reviewer",
    "## agent:linter",
    "## agent:tester",
)


def test_demo_orchestrator_lands_direct_then_merged_twice(tmp_path: Path):
    work = tmp_path / "demo-work"
    # setup.sh hard-codes a default WORK dir; pass our tmp dir instead.
    r = subprocess.run([str(SETUP), str(work)], capture_output=True, check=True)
    assert (work / "task.md").exists(), r.stderr

    # All three slots are present in the seed.
    seed = (work / "task.md").read_text()
    for slot in SEED_SLOTS:
        assert slot in seed, f"missing {slot} in seeded task.md"

    # Run orchestrate.py against the seeded file.
    r = subprocess.run(
        [sys.executable, str(ORCH), str(work / "task.md")],
        capture_output=True,
        check=True,
    )
    out = r.stdout.decode()
    # Order matters: reviewer runs first (direct), then linter+tester (merged).
    assert "agent:reviewer  save: direct" in out, out
    assert "agent:linter    save: merged" in out, out
    assert "agent:tester    save: merged" in out, out

    # The final file has all three agent sections AND no leftover slots.
    final = (work / "task.md").read_text()
    for heading in EXPECTED_HEADINGS:
        assert heading in final, f"missing {heading} in final file"
    for slot in SEED_SLOTS:
        assert slot not in final, f"slot {slot} not replaced"


def test_demo_assets_executable():
    # The shell scripts and python entry points should ship executable.
    paths = (
        DEMO / "setup.sh",
        DEMO / "setup-claude.sh",
        DEMO / "demo.sh",
        DEMO / "demo-claude.sh",
        DEMO / "simple-demo.sh",
        DEMO / "orchestrate.py",
        DEMO / "bg-agent.py",
        DEMO / "bg-claude.py",
        DEMO / "bg-puppeteer.py",
        DEMO / "bg-viewer.sh",
    )
    for path in paths:
        assert path.is_file(), f"missing {path}"
        import stat
        mode = path.stat().st_mode
        assert mode & stat.S_IXUSR, f"{path} not user-executable"


def test_bg_agent_concurrent_yields_direct_then_two_merged(tmp_path: Path):
    """The multi-pane demo's headline cascade. Three bg-agent.py processes
    capture the same base via a barrier, then save with a small jitter so
    reviewer wins `direct` and the other two land `merged` against a
    stale base (via diff3 -m).

    Each agent idles after its save (so its tmux pane keeps showing the
    result), so we read its stdout via non-blocking poll and break as
    soon as all three have written `save:`. This avoids the trap of
    terminating tester before its 0.8 s jitter + save subprocess have
    completed on a slow CI runner.
    """
    import fcntl

    work = tmp_path / "work"
    subprocess.run([str(SETUP), str(work)], capture_output=True, check=True)

    procs = []
    buffers: dict[str, bytes] = {}
    # bg-agent.py defaults to a 2 s pre-open delay so the Emacs viewer
    # pane has time to come up before the cascade. The test doesn't need
    # that wait -- skip it.
    env = {**os.environ, "STILE_DEMO_START_DELAY": "0"}
    for role in ("reviewer", "linter", "tester"):
        p = subprocess.Popen(
            [sys.executable, str(BG_AGENT), role],
            cwd=str(work),
            env=env,
            stdout=subprocess.PIPE,
            stderr=subprocess.PIPE,
        )
        # Make stdout non-blocking so we can poll it.
        flags = fcntl.fcntl(p.stdout.fileno(), fcntl.F_GETFL)
        fcntl.fcntl(p.stdout.fileno(), fcntl.F_SETFL, flags | os.O_NONBLOCK)
        procs.append((role, p))
        buffers[role] = b""

    deadline = time.time() + 20.0  # generous; CI runners can be slow.
    while time.time() < deadline:
        if all(b"save:" in buffers[r] for r, _ in procs):
            break
        for role, p in procs:
            try:
                chunk = p.stdout.read(4096)
                if chunk:
                    buffers[role] += chunk
            except (BlockingIOError, OSError):
                pass
        time.sleep(0.05)

    # Drain anything still in the pipe, then terminate and reap.
    outputs = {}
    for role, p in procs:
        try:
            chunk = p.stdout.read(65536)
            if chunk:
                buffers[role] += chunk
        except (BlockingIOError, OSError):
            pass
        outputs[role] = buffers[role].decode("utf-8", "replace")
        p.terminate()
        try:
            p.wait(timeout=3)
        except subprocess.TimeoutExpired:
            p.kill()

    assert "save: direct" in outputs["reviewer"], outputs["reviewer"]
    assert "save: merged" in outputs["linter"], outputs["linter"]
    assert "save: merged" in outputs["tester"], outputs["tester"]

    final = (work / "task.md").read_text()
    for heading in ("## agent:reviewer", "## agent:linter", "## agent:tester"):
        assert heading in final, f"missing {heading}"
    for slot in ("SLOT_REVIEWER", "SLOT_LINTER", "SLOT_TESTER"):
        assert slot not in final, f"slot {slot} not replaced"


def test_bg_claude_multi_round_with_fake_claude(tmp_path: Path):
    """The Claude-driven multi-round demo. Three bg-claude.py processes
    poll a stile-managed file; when there is a `## user` block they
    haven't responded to yet, they call `claude` (fake mode here, canned
    bodies indexed by round) and `stile save`. After one round, simulate
    the user appending a follow-up via stile and verify all three agents
    respond again."""
    work = tmp_path / "work"
    subprocess.run([str(SETUP_CLAUDE), str(work)], capture_output=True, check=True)

    env = {
        **os.environ,
        "STILE_DEMO_FAKE_CLAUDE": "1",
    }

    procs = []
    for role in ("reviewer", "linter", "tester"):
        p = subprocess.Popen(
            [sys.executable, str(BG_CLAUDE), role],
            cwd=str(work),
            env=env,
            stdout=subprocess.PIPE,
            stderr=subprocess.PIPE,
        )
        procs.append((role, p))

    def _all_three_have(text: str, marker_per_role: dict[str, str]) -> bool:
        return all(marker in text for marker in marker_per_role.values())

    # Round 1: agents see the seeded "## user\nWhat's brittle here?"
    deadline = time.time() + 25.0
    round1_markers = {
        "reviewer": "## agent:reviewer",
        "linter": "## agent:linter",
        "tester": "## agent:tester",
    }
    while time.time() < deadline:
        text = (work / "task.md").read_text()
        if _all_three_have(text, round1_markers):
            break
        time.sleep(0.2)
    text = (work / "task.md").read_text()
    assert _all_three_have(text, round1_markers), text

    # Inject a user follow-up via stile so the agents can't tell the
    # difference between this and the real puppeteer typing in Emacs.
    meta = json.loads(
        subprocess.check_output(
            ["stile", "open", str(work / "task.md"), "--json"]
        )
    )
    base_path = Path(meta["base_path"])
    proposed = (
        base_path.read_text().rstrip("\n")
        + "\n\n## user\nLooking at the linter findings, prioritise.\n"
    )
    save_r = subprocess.run(
        [
            "stile", "save", str(work / "task.md"),
            "--base-sha", meta["base_sha"],
            "--actor", "user",
            "--json",
        ],
        input=proposed.encode(),
        capture_output=True,
        check=False,
    )
    save_result = json.loads(save_r.stdout)
    assert save_result.get("status") == "saved", save_result

    # Round 2: each agent's round-2 canned body has distinct text.
    deadline = time.time() + 25.0
    round2_markers = {
        "reviewer": "Priority by blast-radius",
        "linter": "Suggested fix order",
        "tester": "Test plan after F401",
    }
    while time.time() < deadline:
        text = (work / "task.md").read_text()
        if _all_three_have(text, round2_markers):
            break
        time.sleep(0.2)

    final = (work / "task.md").read_text()
    for marker in round2_markers.values():
        assert marker in final, f"missing round-2 marker: {marker!r}\n\n{final}"

    # Cleanup
    for _role, p in procs:
        p.terminate()
        try:
            p.wait(timeout=3)
        except subprocess.TimeoutExpired:
            p.kill()


