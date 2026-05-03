"""Regression tests for examples/twitter-demo.

Locks in BOTH demo flavours' direct/merged/merged outcome so a future
edit to the seed template, the agents, the barrier logic, or `stile
save`'s branching can't silently break the advertised story.
"""
from __future__ import annotations

import subprocess
import sys
import time
from pathlib import Path

REPO = Path(__file__).resolve().parent.parent.parent
DEMO = REPO / "examples" / "twitter-demo"
SETUP = DEMO / "setup.sh"
ORCH = DEMO / "orchestrate.py"
BG_AGENT = DEMO / "bg-agent.py"

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
        DEMO / "demo.sh",
        DEMO / "simple-demo.sh",
        DEMO / "orchestrate.py",
        DEMO / "bg-agent.py",
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
    """
    work = tmp_path / "work"
    subprocess.run([str(SETUP), str(work)], capture_output=True, check=True)

    # Spawn all three concurrently. Each blocks at the barrier until the
    # other two have captured a base, so spawn order doesn't matter.
    procs = []
    for role in ("reviewer", "linter", "tester"):
        p = subprocess.Popen(
            [sys.executable, str(BG_AGENT), role],
            cwd=str(work),
            stdout=subprocess.PIPE,
            stderr=subprocess.PIPE,
        )
        procs.append((role, p))

    # Each agent prints its save line, then idles forever. Give them up to
    # 10 s to complete the cascade, then terminate and read output.
    deadline = time.time() + 10.0
    while time.time() < deadline:
        # Heuristic: once task.md has all three agent bodies, we're done.
        text = (work / "task.md").read_text()
        if all(slot not in text for slot in ("SLOT_REVIEWER", "SLOT_LINTER", "SLOT_TESTER")):
            break
        time.sleep(0.1)

    outputs = {}
    for role, p in procs:
        p.terminate()
        try:
            out, _err = p.communicate(timeout=3)
        except subprocess.TimeoutExpired:
            p.kill()
            out, _err = p.communicate()
        outputs[role] = out.decode("utf-8", "replace")

    # Reviewer has SAVE_JITTER 0.0 -> first to call stile save -> direct.
    assert "save: direct" in outputs["reviewer"], outputs["reviewer"]
    # Linter and tester have non-zero jitter; they see a stale base and
    # disjoint slots, so diff3 merges them.
    assert "save: merged" in outputs["linter"], outputs["linter"]
    assert "save: merged" in outputs["tester"], outputs["tester"]

    # Final file has all three agent sections and no leftover slots.
    final = (work / "task.md").read_text()
    for heading in ("## agent:reviewer", "## agent:linter", "## agent:tester"):
        assert heading in final, f"missing {heading}"
    for slot in ("SLOT_REVIEWER", "SLOT_LINTER", "SLOT_TESTER"):
        assert slot not in final, f"slot {slot} not replaced"
