#!/usr/bin/env python3
"""Polling agent that responds to user blocks via the `claude` CLI.

Each iteration:
  1. `stile open` to capture a fresh base.
  2. Read the file. Find the most recent `## user` block. If we have not
     yet appended a `## agent:<role>` section AFTER that block, respond.
  3. Build the response by calling `claude --print -p <prompt>` with the
     current file content embedded. Fall back to a canned response if
     the `claude` binary isn't on PATH or `STILE_DEMO_FAKE_CLAUDE` is
     set (used by tests and offline development).
  4. Append the response and `stile save`.

The agent stops doing real work after MAX_ROUNDS responses (safety cap)
and idles, so the recording can linger on the final state.

Usage: bg-claude.py <reviewer|linter|tester>
"""
from __future__ import annotations

import fcntl
import json
import os
import shutil
import subprocess
import sys
import time
from contextlib import contextmanager
from pathlib import Path

POLL_INTERVAL = 2.0
MAX_ROUNDS = 5
USE_FAKE = bool(os.environ.get("STILE_DEMO_FAKE_CLAUDE"))
CLAUDE_TIMEOUT = float(os.environ.get("STILE_DEMO_CLAUDE_TIMEOUT", "60"))

# Agent-level coordination lock. All three agents share this lock so
# their `stile open + save` critical sections serialise. Without it,
# every agent's append-at-end diff would overlap and they'd all conflict
# on round 1; with it, each agent grabs the latest base and saves direct.
COORD_LOCK_PATH = Path.cwd() / ".agent-coord.lock"


@contextmanager
def coord_lock():
    """Serialise the open+save critical section across all agents in this dir."""
    COORD_LOCK_PATH.touch(exist_ok=True)
    with open(COORD_LOCK_PATH, "rb") as fd:
        fcntl.flock(fd.fileno(), fcntl.LOCK_EX)
        try:
            yield
        finally:
            fcntl.flock(fd.fileno(), fcntl.LOCK_UN)

ICONS = {"direct": "✓", "merged": "⚡", "noop": "·", "conflict": "✗"}

# Indexed by [role][round]. If the round index exceeds the list we
# repeat the last entry. Used in fake mode and as a safety net when
# `claude` errors out.
FAKE_BODIES: dict[str, list[str]] = {
    "reviewer": [
        (
            "## agent:reviewer\n"
            "Three concerns:\n"
            "- session token written to disk in plaintext\n"
            "- retry loop has no backoff\n"
            "- logout doesn't lock the session map"
        ),
        (
            "## agent:reviewer\n"
            "Priority by blast-radius:\n"
            "1. Token plaintext (security)\n"
            "2. Logout lock (correctness)\n"
            "3. Retry backoff (robustness)"
        ),
        "## agent:reviewer\nAcknowledged. PR queue ready.",
    ],
    "linter": [
        (
            "## agent:linter\n"
            "12 findings (3 must-fix):\n"
            "- F401 unused import `hmac` at auth.py:4\n"
            "- E501 line too long at auth.py:47\n"
            "- C901 cyclomatic complexity 14 in `_login`"
        ),
        (
            "## agent:linter\n"
            "Suggested fix order:\n"
            "1. F401 (delete line 4)\n"
            "2. E501 (split assignment at line 47)\n"
            "3. C901 (extract `_check_session` from `_login`)"
        ),
        "## agent:linter\nNo new findings.",
    ],
    "tester": [
        (
            "## agent:tester\n"
            "Coverage gaps:\n"
            "- no test for expired-token branch\n"
            "- no test for concurrent logout\n"
            "- no negative test for malformed credentials"
        ),
        (
            "## agent:tester\n"
            "Test plan after F401/E501/C901:\n"
            "- expired-token table-driven test\n"
            "- threaded logout regression\n"
            "- malformed-credentials negative cases"
        ),
        "## agent:tester\nWill ship the suite alongside the fix PR.",
    ],
}


def needs_response(content: str, role: str) -> bool:
    """True iff the latest `## user` block lacks a response from this role."""
    last_user = content.rfind("\n## user")
    if last_user < 0:
        # File starts with `## user` (no leading newline); check from 0.
        last_user = 0 if content.startswith("## user") else -1
        if last_user < 0:
            return False
    after = content[last_user:]
    return f"## agent:{role}" not in after


def call_claude(role: str, content: str) -> str:
    """Run `claude --print -p PROMPT` and return the new section to append."""
    prompt = (
        f"You are agent:{role}, an AI assistant working in a shared text "
        "file alongside a human user (the file is managed by `stile`). "
        "Below is the current content of `task.md`. The user has a "
        f"question or instruction at the most recent `## user` block. "
        f"Append your response as a `## agent:{role}` section. Be "
        "concise (3-6 lines), in your role:\n"
        "- reviewer: code-review concerns and prioritisation\n"
        "- linter: static-analysis findings and style\n"
        "- tester: test coverage gaps and missing tests\n\n"
        f"Output ONLY the new section, starting with `## agent:{role}`. "
        "No preamble, no closing remarks, no codefences.\n\n"
        f"<file>\n{content}\n</file>\n"
    )
    r = subprocess.run(
        ["claude", "--print", "-p", prompt],
        capture_output=True,
        text=True,
        check=True,
        timeout=CLAUDE_TIMEOUT,
    )
    text = r.stdout.strip()
    # Strip codefences if claude added them anyway.
    if text.startswith("```"):
        lines = text.splitlines()
        if lines[0].startswith("```"):
            lines = lines[1:]
        if lines and lines[-1].startswith("```"):
            lines = lines[:-1]
        text = "\n".join(lines).strip()
    return text


def get_response(role: str, content: str, round_idx: int) -> str:
    """Return the new `## agent:role` section for this round."""
    use_fake = USE_FAKE or not shutil.which("claude")
    if not use_fake:
        try:
            return call_claude(role, content)
        except Exception as e:
            print(f"  ✗ claude failed: {e}; using fake", flush=True)
    bodies = FAKE_BODIES[role]
    return bodies[min(round_idx, len(bodies) - 1)]


def main() -> int:
    if len(sys.argv) < 2:
        sys.stderr.write("usage: bg-claude.py <reviewer|linter|tester>\n")
        return 2
    role = sys.argv[1].lower()
    if role not in FAKE_BODIES:
        sys.stderr.write(f"unknown role {role}\n")
        return 2

    label = role
    print(f"agent:{label}")
    print("─" * 28, flush=True)

    rounds_done = 0
    while rounds_done < MAX_ROUNDS:
        # Cheap unlocked poll first so we avoid lock contention when
        # there's nothing to do.
        try:
            meta = json.loads(
                subprocess.check_output(
                    ["stile", "open", "task.md", "--json"], timeout=10,
                )
            )
        except Exception as e:
            print(f"  ✗ open: {e}", flush=True)
            time.sleep(POLL_INTERVAL)
            continue
        content = Path(meta["base_path"]).read_text()
        if not needs_response(content, role):
            time.sleep(POLL_INTERVAL)
            continue

        # Take the agent coord lock; re-check (another agent may have
        # responded in the meantime); compute response from the LATEST
        # base; save. This serialises round writes, so no two agents
        # ever race the trailing-append region.
        with coord_lock():
            try:
                meta = json.loads(
                    subprocess.check_output(
                        ["stile", "open", "task.md", "--json"], timeout=10,
                    )
                )
            except Exception as e:
                print(f"  ✗ open: {e}", flush=True)
                time.sleep(POLL_INTERVAL)
                continue
            content = Path(meta["base_path"]).read_text()
            if not needs_response(content, role):
                # Race with sibling agents -- they got the user block
                # already. Try again next poll cycle.
                continue

            round_idx = rounds_done
            print(f"  · responding (round {round_idx + 1})...", flush=True)
            new_section = get_response(role, content, round_idx)
            proposed = content.rstrip("\n") + "\n\n" + new_section.strip() + "\n"

            try:
                r = subprocess.run(
                    [
                        "stile", "save", "task.md",
                        "--base-sha", meta["base_sha"],
                        "--actor", f"agent:{role}",
                        "--json",
                    ],
                    input=proposed.encode(),
                    capture_output=True,
                    check=False,
                    timeout=10,
                )
                result = json.loads(r.stdout)
            except Exception as e:
                print(f"  ✗ save: {e}", flush=True)
                time.sleep(POLL_INTERVAL)
                continue

        mode = result.get("mode") or result.get("status", "??")
        print(
            f"  {ICONS.get(mode, '?')}  save: {mode} (round {round_idx + 1})",
            flush=True,
        )
        rounds_done += 1
        time.sleep(POLL_INTERVAL)

    # Safety cap reached -- idle so the pane keeps showing results.
    while True:
        time.sleep(60)


if __name__ == "__main__":
    sys.exit(main())
