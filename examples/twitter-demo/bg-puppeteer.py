#!/usr/bin/env python3
"""Drive Emacs via `tmux send-keys` to simulate the user typing in the
demo. The puppeteer is what gives the recording its ping-pong rhythm.

Timeline:
  T=0    print header
  T=15s  type round-2 user follow-up (agents have just finished round 1)
  T=35s  type round-3 wrap-up (agents have just finished round 2)
  idle

Each typed block uses `M->` to move to end-of-buffer, appends a blank
line + a `## user` heading + the body, then `C-x C-s` to save. With
`stile-mode` enabled in the buffer, that save routes through
`stile save` like any other actor.

Usage: bg-puppeteer.py <emacs_pane_id>
"""
from __future__ import annotations

import subprocess
import sys
import time

ROUND_2_FOLLOWUP = (
    "Looking at the linter findings, prioritise the must-fix items and "
    "propose a fix order."
)
ROUND_3_WRAP = "Thanks. Ship it."


def send(pane: str, *keys: str) -> None:
    """Send a sequence of keystrokes to the given tmux pane."""
    subprocess.run(["tmux", "send-keys", "-t", pane, *keys], check=False)


def type_user_block(pane: str, body: str) -> None:
    """Append a `## user` block with `body` at end-of-buffer, then save."""
    keys = ["M->", "Enter", "Enter", "## user", "Enter"]
    for line in body.splitlines():
        keys.extend([line, "Enter"])
    keys.extend(["C-x", "C-s"])
    send(pane, *keys)


def main() -> int:
    if len(sys.argv) < 2:
        sys.stderr.write("usage: bg-puppeteer.py <emacs_pane_id>\n")
        return 2
    pane = sys.argv[1]

    print(f"puppeteer -> {pane}")
    print("─" * 28, flush=True)

    # Round 1 belongs to the agents -- they respond to the seeded ## user
    # block. Real Claude calls take ~3-10 s each, three agents in parallel
    # so ~10-15 s end-to-end. 15 s gives a small buffer.
    print("  · round 1 (agents respond)...", flush=True)
    time.sleep(15)

    print("  ✎ user follow-up (round 2)", flush=True)
    type_user_block(pane, ROUND_2_FOLLOWUP)

    print("  · round 2 (agents respond)...", flush=True)
    time.sleep(20)

    print("  ✎ user wrap (round 3)", flush=True)
    type_user_block(pane, ROUND_3_WRAP)

    print("  ✓ done", flush=True)

    # Idle so the pane keeps showing the timeline.
    while True:
        time.sleep(60)


if __name__ == "__main__":
    sys.exit(main())
