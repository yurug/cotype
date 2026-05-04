#!/usr/bin/env python3
"""Drive Emacs via `tmux send-keys' to simulate a human user typing
into the `## user' section of brainstorm.md across three rounds:

  1. The opening question (challenge brief).
  2. A focusing follow-up after the agents have had a first pass.
  3. The "we're done, thanks" closer.

Each round:
  - `M-x cotype-demo-position-for-user' to land point on a fresh blank
    line in the user section (defined in demo-init.el).
  - `tmux send-keys -l <ch>' per character with a small inter-key
    delay so the typing is visibly human in the recording.
  - `C-x C-s' to save through cotype-mode.

stdout doubles as the visible content of the user pane.

Usage: bg-user.py <emacs_pane_id>
"""
from __future__ import annotations

import subprocess
import sys
import time

# Three messages. Tuned to fit the screen and read as a real user --
# brief, opinionated, ending with an explicit "we're done" so the
# agents idle on the next poll.
ROUND_1 = (
    "Our school is selling crêpes at the end-of-year fair. "
    "300 people, 2 hours, small budget, no big queue. How do we organize it?"
)
ROUND_2 = (
    "Good ideas. What's the single most critical thing to nail "
    "or the whole thing falls apart?"
)
ROUND_3 = (
    "Perfect — we have a plan. Thanks all!"
)

KEY_DELAY = 0.04            # ~25 chars/sec, reads as a brisk human
PRE_TYPE_PAUSE = 0.4        # let the cursor visibly land before typing
SETTLE_AFTER_SAVE = 0.3     # brief pause after C-x C-s


def send(pane: str, *keys: str) -> None:
    """Send named keys (Enter, M-x, C-x, etc.) to `pane`."""
    subprocess.run(["tmux", "send-keys", "-t", pane, *keys], check=False)


def send_literal(pane: str, text: str) -> None:
    """Send `text` LITERALLY (no key-name interpretation)."""
    if not text:
        return
    subprocess.run(["tmux", "send-keys", "-t", pane, "-l", text], check=False)


def type_human(pane: str, text: str, delay: float = KEY_DELAY) -> None:
    """Type `text` char by char with `delay` between characters."""
    for ch in text:
        send_literal(pane, ch)
        time.sleep(delay)


def add_user_message(pane: str, text: str) -> None:
    send(pane, "M-x", "cotype-demo-position-for-user", "Enter")
    time.sleep(PRE_TYPE_PAUSE)
    type_human(pane, text)
    time.sleep(0.2)
    send(pane, "C-x", "C-s")
    time.sleep(SETTLE_AFTER_SAVE)


def header(label: str) -> None:
    print(label, flush=True)
    print("─" * 28, flush=True)


def log(line: str) -> None:
    print(f"  {line}", flush=True)


def main() -> int:
    if len(sys.argv) < 2:
        sys.stderr.write("usage: bg-user.py <emacs_pane_id>\n")
        return 2
    pane = sys.argv[1]

    header(f"user (-> {pane})")

    # Wait for Emacs to come up and cotype-mode to capture its base.
    log("· waiting for Emacs to settle…")
    time.sleep(4)

    log("✎ round 1: posing the challenge")
    add_user_message(pane, ROUND_1)
    log("✓ saved (C-x C-s)")

    # Let the three personas + note-taker do a first pass. Sonnet
    # turns are ~2-4 s; with 4 agents staggered by STAGGER=3 s, the
    # whole round lands in roughly 12-18 s.
    log("· round 1 in flight…")
    time.sleep(28)

    log("✎ round 2: focusing the discussion")
    add_user_message(pane, ROUND_2)
    log("✓ saved (C-x C-s)")

    log("· round 2 in flight…")
    time.sleep(28)

    log("✎ round 3: closing")
    add_user_message(pane, ROUND_3)
    log("✓ saved (C-x C-s)")

    log("· brainstorming complete -- agents will idle")

    # Keep the pane alive so VHS can linger on the final state until
    # demo.tape detaches from tmux and kills the session.
    while True:
        time.sleep(60)


if __name__ == "__main__":
    sys.exit(main())
