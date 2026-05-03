#!/usr/bin/env python3
"""Mock linter agent. Reads stdin, appends a static-analysis section if absent."""
from __future__ import annotations

import sys

content = sys.stdin.read()
marker = "## agent:linter"
if marker in content:
    sys.stdout.write(content)
    sys.exit(0)
sys.stdout.write(content.rstrip("\n") + "\n\n" + marker + "\n"
    "Static analysis: 12 findings (3 must-fix).\n"
    "- F401  unused import `hmac` at auth.py:4\n"
    "- E501  line too long at auth.py:47 (123 > 88)\n"
    "- C901  cyclomatic complexity 14 in `_login` (limit 10)\n"
)
