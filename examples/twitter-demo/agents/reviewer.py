#!/usr/bin/env python3
"""Mock reviewer agent. Reads stdin, appends a review section if absent."""
from __future__ import annotations

import sys

content = sys.stdin.read()
marker = "## agent:reviewer"
if marker in content:
    sys.stdout.write(content)
    sys.exit(0)
sys.stdout.write(content.rstrip("\n") + "\n\n" + marker + "\n"
    "Three concerns:\n"
    "- session token written to disk in plaintext\n"
    "- retry loop has no backoff\n"
    "- logout doesn't lock the session map\n"
)
