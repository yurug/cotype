#!/usr/bin/env python3
"""Mock tester agent. Reads stdin, appends a coverage-gaps section if absent."""
from __future__ import annotations

import sys

content = sys.stdin.read()
marker = "## agent:tester"
if marker in content:
    sys.stdout.write(content)
    sys.exit(0)
sys.stdout.write(content.rstrip("\n") + "\n\n" + marker + "\n"
    "Coverage gaps:\n"
    "- no test for expired-token branch\n"
    "- no test for concurrent logout\n"
    "- no negative test for malformed credentials\n"
)
