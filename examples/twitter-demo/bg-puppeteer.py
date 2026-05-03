#!/usr/bin/env python3
"""Drive Emacs via `tmux send-keys` to simulate a user editing the
`## requirements` section of the rocket-build doc.

Strategy: invoke the helper Emacs command we defined in `demo-init.el`:

    M-x stile-demo-add-requirement RET <text> RET

That elisp helper inserts a new bullet at the end of the `## requirements`
section and calls `save-buffer`, which `stile-mode` routes through
`stile save`. Concurrent agents are editing other sections; their saves
and ours produce disjoint diffs and `stile`'s `diff3 -m` merges them.

Timeline:
  T=0    print header
  T=12s  type round-2 follow-up: an absurd-but-valid requirement
  T=27s  type round-3 follow-up: a tighter-budget requirement

The exact wait times are tuned so the agents (which depend on the
section the user just edited) have a window to react before the next
user change.

Usage: bg-puppeteer.py <emacs_pane_id>
"""
from __future__ import annotations

import subprocess
import sys
import time

ROUND_2_REQUIREMENT = "must survive a 5-year-old throwing it at a wall"
ROUND_3_REQUIREMENT = "BOM under $5 (no NASA contracts)"


def send(pane: str, *keys: str) -> None:
    """Send a sequence of key events to the given tmux pane."""
    subprocess.run(["tmux", "send-keys", "-t", pane, *keys], check=False)


def add_requirement(pane: str, text: str) -> None:
    """Run the Emacs helper that inserts `text` as a bullet under
    `## requirements` and saves the buffer through stile-mode."""
    # M-x stile-demo-add-requirement RET <text> RET
    keys = [
        "M-x", "stile-demo-add-requirement", "Enter",
        text, "Enter",
    ]
    send(pane, *keys)


def main() -> int:
    if len(sys.argv) < 2:
        sys.stderr.write("usage: bg-puppeteer.py <emacs_pane_id>\n")
        return 2
    pane = sys.argv[1]

    print(f"puppeteer -> {pane}")
    print("─" * 28, flush=True)

    print("  · round 1 (agents react to seed requirements)...", flush=True)
    time.sleep(12)

    print(f"  ✎ user adds: {ROUND_2_REQUIREMENT!r}", flush=True)
    add_requirement(pane, ROUND_2_REQUIREMENT)

    print("  · round 2 (engineer adapts; tester/marketer cascade)...", flush=True)
    time.sleep(15)

    print(f"  ✎ user adds: {ROUND_3_REQUIREMENT!r}", flush=True)
    add_requirement(pane, ROUND_3_REQUIREMENT)

    print("  · round 3 (full cascade)...", flush=True)
    time.sleep(10)

    print("  ✓ done", flush=True)

    while True:
        time.sleep(60)


if __name__ == "__main__":
    sys.exit(main())
