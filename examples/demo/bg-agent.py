#!/usr/bin/env python3
"""Background agent for one tmux pane in the Twitter demo.

Captures a base via `cotype open`, waits at a barrier until all three
agents have captured (so they all hold the SAME base_sha), then saves
its proposed bytes. The first save that grabs the sidecar lock lands
`direct`; the others see a stale base + disjoint diffs and cotype
3-way merges them. A small post-barrier jitter makes the cascade
visible in the recording.

Usage: bg-agent.py <reviewer|linter|tester>
"""
from __future__ import annotations

import json
import os
import subprocess
import sys
import time
from pathlib import Path

BODIES = {
    "REVIEWER": (
        "Three concerns:\n"
        "- session token written to disk in plaintext\n"
        "- retry loop has no backoff\n"
        "- logout doesn't lock the session map"
    ),
    "LINTER": (
        "12 findings (3 must-fix):\n"
        "- F401 unused import `hmac` at auth.py:4\n"
        "- E501 line too long at auth.py:47\n"
        "- C901 cyclomatic complexity 14 in `_login`"
    ),
    "TESTER": (
        "Coverage gaps:\n"
        "- no test for expired-token branch\n"
        "- no test for concurrent logout\n"
        "- no negative test for malformed credentials"
    ),
}

# Lives inside the working dir; setup.sh wipes the working dir on every run.
BARRIER_DIR = Path.cwd() / ".cotype-demo-barrier"
N_AGENTS = 3

# Pre-open delay so the Emacs viewer pane has time to start up and
# enable cotype-mode BEFORE agents start saving (otherwise the cascade
# would happen before Emacs finishes loading and the viewer would attach
# to an already-populated file). Override to 0 in tests via env var.
START_DELAY = float(os.environ.get("COTYPE_DEMO_START_DELAY", "2.0"))

# Post-barrier jitter so the three saves cascade visibly in the recording.
SAVE_JITTER = {"reviewer": 0.0, "linter": 0.4, "tester": 0.8}

ICONS = {"direct": "✓", "merged": "⚡", "noop": "·"}


def wait_for_barrier(role: str) -> None:
    """Mark this agent as having captured a base; wait for the other N-1."""
    BARRIER_DIR.mkdir(parents=True, exist_ok=True)
    (BARRIER_DIR / f"{role}.opened").touch()
    while len(list(BARRIER_DIR.glob("*.opened"))) < N_AGENTS:
        time.sleep(0.05)


def main() -> int:
    if len(sys.argv) < 2:
        sys.stderr.write("usage: bg-agent.py <role>\n")
        return 2
    role = sys.argv[1].lower()
    if role.upper() not in BODIES:
        sys.stderr.write(f"unknown role {role}\n")
        return 2

    print(f"agent:{role}")
    print("─" * 18, flush=True)

    if START_DELAY > 0:
        time.sleep(START_DELAY)

    try:
        # Phase 1 -- everyone captures a base.
        meta = json.loads(
            subprocess.check_output(["cotype", "open", "task.md", "--json"])
        )
        base_sha_short = meta["base_sha"].split(":", 1)[1][:8]
        base_bytes = Path(meta["base_path"]).read_bytes()
        proposed = base_bytes.replace(
            f"SLOT_{role.upper()}".encode(),
            BODIES[role.upper()].encode(),
        )
        print(f"  ·  open  (base {base_sha_short}…)", flush=True)

        # Phase 2 -- wait for the others.
        wait_for_barrier(role)

        # Phase 3 -- visible cascade, then save.
        time.sleep(SAVE_JITTER.get(role, 0.0))
        r = subprocess.run(
            [
                "cotype", "save", "task.md",
                "--base-sha", meta["base_sha"],
                "--actor", f"agent:{role}",
                "--json",
            ],
            input=proposed,
            capture_output=True,
        )
        result = json.loads(r.stdout)
    except Exception as e:
        print(f"  ✗  error: {e}", flush=True)
        time.sleep(60)
        return 1

    mode = result.get("mode") or result.get("status", "??")
    print(f"  {ICONS.get(mode, '✗')}  save: {mode}", flush=True)

    # Idle so the pane keeps showing the result.
    while True:
        time.sleep(60)


if __name__ == "__main__":
    sys.exit(main())
