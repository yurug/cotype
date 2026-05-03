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


def test_demo_claude_roles_match_bg_claude():
    """`demo-claude.sh` may only spawn role names that bg-claude.py
    understands. Catches the exact slip we just shipped: when the
    bg-claude role set was renamed (reviewer/linter/tester -> engineer/
    tester/marketer), demo-claude.sh kept the old names and two of three
    panes silently exited at startup."""
    import re

    sh_text = (DEMO / "demo-claude.sh").read_text()
    invoked = set(re.findall(r"bg-claude\.py'?\s+(\w+)", sh_text))
    assert invoked, "no bg-claude.py invocations found in demo-claude.sh"

    py_text = (DEMO / "bg-claude.py").read_text()
    # Roles are the keys of the DEPENDENCIES dict.
    deps_match = re.search(r"DEPENDENCIES\s*=\s*\{(.+?)\}", py_text, re.DOTALL)
    assert deps_match, "could not find DEPENDENCIES dict in bg-claude.py"
    valid = set(re.findall(r'"(\w+)"\s*:', deps_match.group(1)))
    assert valid, "could not extract roles from DEPENDENCIES dict"

    bad = invoked - valid
    assert not bad, (
        f"demo-claude.sh invokes unknown roles: {sorted(bad)}; "
        f"bg-claude.py knows: {sorted(valid)}"
    )


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


def test_bg_claude_multi_round_section_based(tmp_path: Path):
    """Section-based Claude demo: each agent OWNS one section and READS
    another. When the dependency section changes, the agent regenerates
    its own section body.

    The pedagogical scenario is collaboratively designing
    `sum_evens(xs)`. User owns `## spec`; agents own `## code`,
    `## tests`, `## docs`. We assert:

      round 1: code/tests/docs all populate their sections in response
               to the seed `## spec`.
      round 2: when the user appends a stricter spec line, the code
               agent regenerates `## code`, and tests+docs cascade off
               the new `## code` section.
    """
    work = tmp_path / "work"
    subprocess.run([str(SETUP_CLAUDE), str(work)], capture_output=True, check=True)

    env = {**os.environ, "STILE_DEMO_FAKE_CLAUDE": "1"}

    procs = []
    for role in ("code", "tests", "docs"):
        # The agent's polling loop prints a status line per cycle. Across
        # several rounds with three agents that adds up; on a slow runner
        # the captured PIPE buffer can fill and block the writers
        # (intermittent dead-lock on macOS). We assert on file content,
        # not on the agents' stdout, so route both streams to DEVNULL.
        p = subprocess.Popen(
            [sys.executable, str(BG_CLAUDE), role],
            cwd=str(work),
            env=env,
            stdout=subprocess.DEVNULL,
            stderr=subprocess.DEVNULL,
        )
        procs.append((role, p))

    def _wait_for(markers: dict[str, str], deadline: float) -> bool:
        while time.time() < deadline:
            text = (work / "task.md").read_text()
            if all(m in text for m in markers.values()):
                return True
            time.sleep(0.2)
        return False

    # Round 1: distinctive substrings from each round-0 canned body.
    # Generous deadline because macOS CI runners can be 5-10x slower at
    # subprocess-heavy work than the Linux ones.
    round1 = {
        "code":  "def sum_evens(xs):",
        "tests": "assert sum_evens([1, 2, 3, 4]) == 6",
        "docs":  "Empty input returns 0",
    }
    assert _wait_for(round1, time.time() + 60.0), \
        (work / "task.md").read_text()

    # Edit `## spec` directly (simulating the puppeteer's helper).
    sys_path = sys.path[:]
    sys.path.insert(0, str(REPO / "examples" / "twitter-demo"))
    try:
        import importlib.util
        spec = importlib.util.spec_from_file_location("bg_claude", BG_CLAUDE)
        bg_claude = importlib.util.module_from_spec(spec)
        spec.loader.exec_module(bg_claude)
    finally:
        sys.path = sys_path

    meta = json.loads(
        subprocess.check_output(
            ["stile", "open", str(work / "task.md"), "--json"]
        )
    )
    base_path = Path(meta["base_path"])
    content = base_path.read_text()
    new_spec_body = (
        bg_claude.section_body(content, "spec").rstrip("\n")
        + "\n- Reject non-integer input with ValueError.\n"
    )
    proposed = bg_claude.replace_section_body(content, "spec", new_spec_body)
    save_r = subprocess.run(
        [
            "stile", "save", str(work / "task.md"),
            "--base-sha", meta["base_sha"],
            "--actor", "user",
            "--json",
        ],
        input=proposed.encode(),
        capture_output=True, check=False,
    )
    save_result = json.loads(save_r.stdout)
    assert save_result.get("status") == "saved", save_result

    # Round 2: each agent's round-1 canned body has distinct text.
    round2 = {
        "code":  'raise ValueError(f"non-integer:',
        "tests": 'except ValueError:',
        "docs":  'Raises `ValueError`',
    }
    assert _wait_for(round2, time.time() + 60.0), \
        (work / "task.md").read_text()

    final = (work / "task.md").read_text()
    # Each section heading must appear exactly once -- agents replace
    # bodies in place rather than appending new copies.
    for header in ("## spec", "## code", "## tests", "## docs"):
        assert final.count(header) == 1, f"{header!r} count != 1\n{final}"

    for _role, p in procs:
        p.terminate()
        try:
            p.wait(timeout=3)
        except subprocess.TimeoutExpired:
            p.kill()


