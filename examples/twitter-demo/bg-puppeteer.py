#!/usr/bin/env python3
"""Drive Emacs via `tmux send-keys` to simulate a human user editing
the `## spec` section.

Unlike the previous one-shot `M-x stile-demo-add-spec` flow, this
typist actually pecks at the keyboard: per-character `tmux send-keys -l
<ch>` calls with a small inter-character delay. The viewer sees the
text appear letter by letter inside Emacs, which makes the `user` role
visible and obvious.

Sequence per round:
  1. `M-x stile-demo-position-for-spec RET`
       -- a small elisp helper in demo-init.el moves point to the end
          of the `## spec` bullet list and pre-types the leading "- ".
  2. Type the bullet text, char by char.
  3. `C-x C-s` -- save the buffer; stile-mode routes the write through
     `stile save`.

The puppeteer's stdout doubles as the "user" pane content.

Usage: bg-puppeteer.py <emacs_pane_id>
"""
from __future__ import annotations

import subprocess
import sys
import time

ROUND_2_LINE = "Reject non-integer input with ValueError."
ROUND_3_LINE = "Accept any iterable, not just a list."

# Time between key events when the puppeteer is "typing". 0.05s gives
# ~20 chars per second -- reads as a brisk human, not a robot, and
# keeps the recording legible.
KEY_DELAY = 0.05

# Pause before each typed bullet so viewers can see the cursor jump
# into position before the first character lands.
PRE_TYPE_PAUSE = 0.4


def send(pane: str, *keys: str) -> None:
    """Send a sequence of named keys (Enter, M-x, C-x, etc.) to `pane`."""
    subprocess.run(["tmux", "send-keys", "-t", pane, *keys], check=False)


def send_literal(pane: str, text: str) -> None:
    """Send `text` LITERALLY (no key-name interpretation)."""
    if not text:
        return
    subprocess.run(["tmux", "send-keys", "-t", pane, "-l", text], check=False)


def type_human(pane: str, text: str, delay: float = KEY_DELAY) -> None:
    """Type `text` char by char with `delay` between each character."""
    for ch in text:
        send_literal(pane, ch)
        time.sleep(delay)


def add_bullet(pane: str, text: str) -> None:
    # 1. invoke the position helper -- cursor lands at end of ## spec,
    #    "- " prefix already in place.
    send(pane, "M-x", "stile-demo-position-for-spec", "Enter")
    time.sleep(PRE_TYPE_PAUSE)
    # 2. type the bullet text visibly.
    type_human(pane, text)
    # 3. save through stile-mode.
    time.sleep(0.2)
    send(pane, "C-x", "C-s")


def header(label: str) -> None:
    print(label, flush=True)
    print("─" * 28, flush=True)


def log(line: str) -> None:
    print(f"  {line}", flush=True)


def main() -> int:
    if len(sys.argv) < 2:
        sys.stderr.write("usage: bg-puppeteer.py <emacs_pane_id>\n")
        return 2
    pane = sys.argv[1]

    header(f"user (-> {pane})")

    log("· round 1 — agents react to seed")
    time.sleep(12)

    log("✎ typing in ## spec…")
    log(f"  {ROUND_2_LINE!r}")
    add_bullet(pane, ROUND_2_LINE)
    log("✓ saved (C-x C-s)")

    log("· round 2 — code adapts; tests/docs cascade")
    time.sleep(15)

    log("✎ typing in ## spec…")
    log(f"  {ROUND_3_LINE!r}")
    add_bullet(pane, ROUND_3_LINE)
    log("✓ saved (C-x C-s)")

    log("· round 3 — full cascade")
    time.sleep(10)

    log("✓ done")

    while True:
        time.sleep(60)


if __name__ == "__main__":
    sys.exit(main())
