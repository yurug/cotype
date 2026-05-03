#!/usr/bin/env python3
"""A deterministic mock agent for testing stile-driven workflows offline.

Behaviour:
  - Reads the file content from stdin.
  - Counts top-level '## user' and '## agent' headings.
  - If user_count > agent_count, appends a new '## agent (mock #N)' block.
  - Otherwise outputs stdin unchanged (so `stile save` becomes a noop).

Output is fully deterministic given the input -- same input bytes in,
same output bytes out -- which is what makes the loop testable. A real
LLM driver replaces this script; the contract is just:

    real_agent < base_bytes  > proposed_bytes
"""
from __future__ import annotations

import sys


def main() -> int:
    content = sys.stdin.read()
    lines = content.splitlines()
    user_count = sum(1 for ln in lines if ln.startswith("## user"))
    agent_count = sum(1 for ln in lines if ln.startswith("## agent"))

    if user_count <= agent_count:
        # Nothing new to answer; emit unchanged so the save short-circuits.
        sys.stdout.write(content)
        return 0

    reply = (
        f"\n## agent (mock #{user_count})\n"
        f"Acknowledged user block #{user_count}. "
        f"This is a deterministic mock -- replace agent_mock.py with a real LLM.\n"
    )
    out = content.rstrip("\n") + "\n" + reply
    sys.stdout.write(out)
    return 0


if __name__ == "__main__":
    sys.exit(main())
