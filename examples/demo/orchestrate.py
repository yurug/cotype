#!/usr/bin/env python3
"""Drive three agents through cotype against a single shared base.

Used by the Twitter demo. The seeded `task.md` has a placeholder line per
agent (SLOT_REVIEWER / SLOT_LINTER / SLOT_TESTER); each agent reads from
the same base_sha and replaces only its own slot, producing one direct
save followed by two merged saves -- the exact "concurrent edits, no
lost work" story the demo advertises.

Usage:
    orchestrate.py FILE       # idempotent; prints one line per agent
"""
from __future__ import annotations

import json
import subprocess
import sys
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


def cotype(*args: str, stdin: bytes = b"") -> dict:
    p = subprocess.run(
        ["cotype", *args], input=stdin, capture_output=True, check=False
    )
    if p.stdout:
        try:
            return json.loads(p.stdout)
        except json.JSONDecodeError:
            pass
    return {"status": "error", "error": "??", "message": p.stderr.decode()}


def main() -> int:
    if len(sys.argv) < 2:
        sys.stderr.write("usage: orchestrate.py FILE\n")
        return 2
    target = sys.argv[1]

    # Capture ONE base; all three agents share it.  This is the key to the
    # demo: the second and third saves see a stale base + non-overlapping
    # diffs, so cotype reports `merged` rather than `direct`.
    meta = cotype("open", target, "--json")
    base_sha = meta["base_sha"]
    base_bytes = Path(meta["base_path"]).read_bytes()

    for role in ("REVIEWER", "LINTER", "TESTER"):
        proposed = base_bytes.replace(
            f"SLOT_{role}".encode(), BODIES[role].encode()
        )
        result = cotype(
            "save", target,
            "--base-sha", base_sha,
            "--actor", f"agent:{role.lower()}",
            "--json",
            stdin=proposed,
        )
        mode = result.get("mode") or result.get("status", "??")
        print(f"  agent:{role.lower():<9} save: {mode}")
    return 0


if __name__ == "__main__":
    sys.exit(main())
