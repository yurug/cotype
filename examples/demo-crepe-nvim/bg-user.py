#!/usr/bin/env python3
"""Drive neovim via `tmux send-keys' to simulate a human user typing
into the `## user' section of brainstorm.md across three rounds:

  1. The opening question (challenge brief).
  2. A focusing follow-up after the agents have had a first pass.
  3. The "we're done, thanks" closer.

Each round:
  - `<Esc>` to ensure normal mode.
  - `:CotypeDemoPositionForUser<CR>` -- the helper in demo-init.vim
    positions the cursor and enters insert mode.
  - Type the message char-by-char (we're now in insert mode).
  - `<Esc>` to leave insert mode.
  - `:w<CR>` to save through the cotype vim plugin.

stdout doubles as the visible content of the user pane.

Usage: bg-user.py <nvim_pane_id>
"""
from __future__ import annotations

import subprocess
import sys
import time

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

KEY_DELAY = 0.04            # ~25 chars/sec
PRE_TYPE_PAUSE = 0.4
SETTLE_AFTER_SAVE = 0.3


def send(pane: str, *keys: str) -> None:
    """Send named keys (Enter, Escape, etc.) to `pane`."""
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
    # 1. ensure we're in normal mode and trigger the position helper
    #    (which pauses the cotype auto-revert timer for this buffer
    #    so a checktime tick doesn't race with the keystrokes below).
    send(pane, "Escape")
    time.sleep(0.1)
    send_literal(pane, ":CotypeDemoPositionForUser")
    send(pane, "Enter")
    time.sleep(PRE_TYPE_PAUSE)
    # 2. helper put cursor at the right line + entered insert mode.
    type_human(pane, text)
    time.sleep(0.2)
    # 3. leave insert mode, save through cotype-mode (BufWriteCmd),
    #    and resume the auto-revert timer in the same Ex chain so
    #    agent writes start being picked up again immediately.
    send(pane, "Escape")
    time.sleep(0.15)
    send_literal(pane, ":w | CotypeDemoResumeTimer")
    send(pane, "Enter")
    time.sleep(SETTLE_AFTER_SAVE)


def header(label: str) -> None:
    print(label, flush=True)
    print("─" * 28, flush=True)


def log(line: str) -> None:
    print(f"  {line}", flush=True)


def main() -> int:
    if len(sys.argv) < 2:
        sys.stderr.write("usage: bg-user.py <nvim_pane_id>\n")
        return 2
    pane = sys.argv[1]

    header(f"user (-> {pane})")

    # Wait for nvim to come up and the cotype plugin to capture its base.
    log("· waiting for nvim to settle…")
    time.sleep(4)

    log("✎ round 1: posing the challenge")
    add_user_message(pane, ROUND_1)
    log("✓ saved (:w)")

    # Let the four agents do a first pass.
    log("· round 1 in flight…")
    time.sleep(28)

    log("✎ round 2: focusing the discussion")
    add_user_message(pane, ROUND_2)
    log("✓ saved (:w)")

    log("· round 2 in flight…")
    time.sleep(28)

    log("✎ round 3: closing")
    add_user_message(pane, ROUND_3)
    log("✓ saved (:w)")

    log("· brainstorming complete -- agents will idle")

    # Keep the pane alive so VHS can linger on the final state until
    # demo.tape detaches from tmux.
    while True:
        time.sleep(60)


if __name__ == "__main__":
    sys.exit(main())
