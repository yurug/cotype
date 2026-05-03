#!/usr/bin/env python3
"""Drive Emacs via `tmux send-keys` to simulate the user editing the
`## spec` section of the sum_evens design doc.

Strategy: invoke the helper Emacs command we defined in `demo-init.el`:

    M-x stile-demo-add-spec RET <text> RET

That elisp helper inserts a new bullet at the end of the `## spec`
section and calls `save-buffer`, which `stile-mode` routes through
`stile save`. Concurrent agents are editing other sections; their saves
and ours produce disjoint diffs that `diff3 -m` merges cleanly.

Timeline:
  T=0    print header
  T=12s  add round-2 spec line: stricter input handling
  T=27s  add round-3 spec line: looser input shape

Usage: bg-puppeteer.py <emacs_pane_id>
"""
from __future__ import annotations

import subprocess
import sys
import time

ROUND_2_SPEC_LINE = "Reject non-integer input with ValueError."
ROUND_3_SPEC_LINE = "Accept any iterable, not just a list."


def send(pane: str, *keys: str) -> None:
    """Send a sequence of key events to the given tmux pane."""
    subprocess.run(["tmux", "send-keys", "-t", pane, *keys], check=False)


def add_spec(pane: str, text: str) -> None:
    """Run the Emacs helper that inserts `text` as a bullet under
    `## spec` and saves the buffer through stile-mode."""
    keys = [
        "M-x", "stile-demo-add-spec", "Enter",
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

    print("  · round 1 (agents react to seed spec)...", flush=True)
    time.sleep(12)

    print(f"  ✎ user adds: {ROUND_2_SPEC_LINE!r}", flush=True)
    add_spec(pane, ROUND_2_SPEC_LINE)

    print("  · round 2 (code adapts; tests/docs cascade)...", flush=True)
    time.sleep(15)

    print(f"  ✎ user adds: {ROUND_3_SPEC_LINE!r}", flush=True)
    add_spec(pane, ROUND_3_SPEC_LINE)

    print("  · round 3 (full cascade)...", flush=True)
    time.sleep(10)

    print("  ✓ done", flush=True)

    while True:
        time.sleep(60)


if __name__ == "__main__":
    sys.exit(main())
