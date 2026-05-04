#!/usr/bin/env python3
"""Polling agent for the multi-section collaborative-coding demo.

Each agent OWNS one Markdown section in `task.md` and READS another.
On every poll cycle the agent computes the SHA-256 of its dependency
section; if it differs from what the agent last reacted to, the agent
regenerates the BODY of its own section and submits the whole document
to `cotype save`. Different actors edit different sections, so concurrent
saves are disjoint diffs that cotype's `diff3 -m` merges cleanly -- the
first save lands `direct`, subsequent ones land `merged`.

Roles for this demo (collaboratively design `sum_evens(xs)`):

  code    reads `## spec`   writes `## code`     (the implementation)
  tests   reads `## code`   writes `## tests`    (the assertions)
  docs    reads `## code`   writes `## docs`     (the docstring)

Real LLM responses come from the `claude` CLI when it is on PATH;
otherwise (and when COTYPE_DEMO_FAKE_CLAUDE=1) the agent uses canned
per-round bodies indexed by how many rounds it has performed.

Usage: bg-claude.py <code|tests|docs>
"""
from __future__ import annotations

import hashlib
import json
import os
import re
import shutil
import subprocess
import sys
import time
from pathlib import Path

POLL_INTERVAL = 1.0
MAX_ROUNDS = 5
USE_FAKE = bool(os.environ.get("COTYPE_DEMO_FAKE_CLAUDE"))
CLAUDE_TIMEOUT = float(os.environ.get("COTYPE_DEMO_CLAUDE_TIMEOUT", "60"))

# Each role's input section is the section it reacts to. Role names
# match the section the role writes (so `bg-claude.py code` writes to
# `## code` and reads `## spec`).
DEPENDENCIES = {
    "code":  "spec",
    "tests": "code",
    "docs":  "code",
}

ICONS = {"direct": "✓", "merged": "⚡", "noop": "·", "conflict": "✗"}

# Canned bodies per role per round. Round 0 reacts to the seed spec
# (one bullet). Round 1 reacts to spec + "Reject non-integer input
# with ValueError." Round 2 reacts to spec + "Accept any iterable,
# not just a list."
FAKE_BODIES = {
    "code": [
        "```python\n"
        "def sum_evens(xs):\n"
        "    return sum(x for x in xs if x % 2 == 0)\n"
        "```",

        "```python\n"
        "def sum_evens(xs):\n"
        "    for x in xs:\n"
        "        if not isinstance(x, int) or isinstance(x, bool):\n"
        "            raise ValueError(f\"non-integer: {x!r}\")\n"
        "    return sum(x for x in xs if x % 2 == 0)\n"
        "```",

        "```python\n"
        "def sum_evens(xs):\n"
        "    total = 0\n"
        "    for x in xs:\n"
        "        if not isinstance(x, int) or isinstance(x, bool):\n"
        "            raise ValueError(f\"non-integer: {x!r}\")\n"
        "        if x % 2 == 0:\n"
        "            total += x\n"
        "    return total\n"
        "```",
    ],
    "tests": [
        "```python\n"
        "assert sum_evens([1, 2, 3, 4]) == 6\n"
        "assert sum_evens([]) == 0\n"
        "```",

        "```python\n"
        "assert sum_evens([1, 2, 3, 4]) == 6\n"
        "assert sum_evens([]) == 0\n"
        "try:\n"
        "    sum_evens([1, \"two\"])\n"
        "except ValueError:\n"
        "    pass\n"
        "else:\n"
        "    raise AssertionError(\"expected ValueError\")\n"
        "```",

        "```python\n"
        "assert sum_evens([1, 2, 3, 4]) == 6\n"
        "assert sum_evens([]) == 0\n"
        "assert sum_evens(iter([2, 4, 6])) == 12\n"
        "try:\n"
        "    sum_evens([1, \"two\"])\n"
        "except ValueError:\n"
        "    pass\n"
        "else:\n"
        "    raise AssertionError(\"expected ValueError\")\n"
        "```",
    ],
    "docs": [
        "Return the sum of the even integers in `xs`. Empty input returns 0.",

        "Return the sum of the even integers in `xs`. "
        "Raises `ValueError` if any element is not an `int`.",

        "Sum the even integers in `xs`. Accepts any iterable of `int`; "
        "raises `ValueError` on non-integer elements.",
    ],
}


# -- doc parsing / rewriting -------------------------------------------------

_HEADER_RE = re.compile(r"^## (.+?)\s*$", re.MULTILINE)


def parse_sections(content: str) -> tuple[str, list[tuple[str, str]]]:
    """Return (preamble, [(name, body), ...]) where `body` is the section's
    inner content with leading/trailing blank-line whitespace stripped.

    Storing bodies in a *canonical* (stripped) form is the only way to
    make `parse_sections` and `render_doc` exact inverses of the seed
    file's layout. If they aren't inverses, every agent's save subtly
    reformats sections it didn't touch (e.g. the blank line between
    header and body silently disappears), the diff suddenly spans the
    whole document, and concurrent saves on different sections start
    conflicting because their hunks land in adjacent regions instead of
    disjoint ones.
    """
    matches = list(_HEADER_RE.finditer(content))
    if not matches:
        return content, []
    preamble = content[: matches[0].start()]
    sections: list[tuple[str, str]] = []
    for i, m in enumerate(matches):
        name = m.group(1).strip()
        body_start = m.end()
        body_end = matches[i + 1].start() if i + 1 < len(matches) else len(content)
        body = content[body_start:body_end].strip("\n")
        sections.append((name, body))
    return preamble, sections


def render_doc(preamble: str, sections: list[tuple[str, str]]) -> str:
    """Render to the canonical layout used by the seed file:

      <preamble>
      ## name1
      <blank line>
      <body1>
      <blank line>
      <blank line>
      ## name2
      <blank line>
      <body2>
      ...
      ## nameN
      <blank line>
      <bodyN>
      <single trailing newline>

    With this layout, `render_doc(*parse_sections(seed))` is exactly
    `seed` -- a property the bg-agent test relies on so that concurrent
    saves don't accidentally diff against each other.
    """
    out = [preamble]
    n = len(sections)
    for i, (name, body) in enumerate(sections):
        out.append(f"## {name}\n\n{body}\n")
        if i < n - 1:
            out.append("\n\n")  # two blank lines between sections
    return "".join(out)


def replace_section_body(content: str, target: str, new_body: str) -> str:
    """Replace the body of `## target` with `new_body`. Bodies are stored
    canonically (stripped); render adds the separators."""
    preamble, sections = parse_sections(content)
    canonical = new_body.strip("\n")
    for i, (name, _body) in enumerate(sections):
        if name == target:
            sections[i] = (name, canonical)
            break
    rendered = render_doc(preamble, sections)
    # Paranoid invariant: rendered output should contain every section we
    # parsed. We log loudly but DON'T crash the agent -- a hard `assert`
    # here turns a flake into a stuck demo with no diagnostic, while a
    # log line (visible in the agent's per-pane stdout) preserves the
    # information without killing the test.
    _, rendered_sections = parse_sections(rendered)
    in_set = {n for n, _ in sections}
    out_set = {n for n, _ in rendered_sections}
    if in_set != out_set:
        sys.stderr.write(
            f"WARN: replace_section_body section drift: "
            f"input={sorted(in_set)} output={sorted(out_set)}\n"
        )
    return rendered


def section_body(content: str, name: str) -> str:
    """Return the body of `## name`, or '' if absent."""
    _, sections = parse_sections(content)
    for n, body in sections:
        if n == name:
            return body
    return ""


def section_hash(content: str, name: str) -> str:
    return hashlib.sha256(section_body(content, name).encode("utf-8")).hexdigest()


def is_placeholder(body: str) -> bool:
    """True iff this section body is just the seed placeholder.

    The seed file uses bodies like `(no implementation yet -- waiting on
    spec)`. Downstream agents must wait until their dependency section
    is actually filled in -- otherwise they'd react to the placeholder
    text and burn their round-0 canned body on it."""
    stripped = body.strip()
    return not stripped or stripped.startswith("(no ")


# -- response generation ----------------------------------------------------

def call_claude(role: str, content: str) -> str:
    dep = DEPENDENCIES[role]
    role_hint = {
        "code":  "Write a concise Python implementation of `sum_evens(xs)` "
                 "in a fenced ```python``` block. No explanation around it.",
        "tests": "Write executable Python assertions exercising "
                 "`sum_evens` in a fenced ```python``` block. No "
                 "explanation around it.",
        "docs":  "Write a concise one- or two-sentence docstring (plain "
                 "prose, no fences). Just the docstring text.",
    }[role]
    prompt = (
        f"You are agent:{role} working in a shared Markdown document called "
        "`task.md` alongside a human user. The file is managed by `cotype`. "
        f"Your job: write the BODY of the `## {role}` section, reacting to "
        f"the current `## {dep}` section. Be concise. "
        "Output ONLY the body (no header, no preamble, no closing remarks). "
        f"Stay in your role: {role_hint}\n\n"
        f"<file>\n{content}\n</file>\n"
    )
    r = subprocess.run(
        ["claude", "--print", "-p", prompt],
        capture_output=True, text=True, check=True, timeout=CLAUDE_TIMEOUT,
    )
    return r.stdout.strip()


def _spec_bullet_count(content: str) -> int:
    """Count `- ` bullet lines in the `## spec` section.

    The user drives the cascade by adding bullets here; counting them
    gives a deterministic, race-free notion of "which round we're in":
    1 bullet = round 0, 2 = round 1, 3 = round 2. If a downstream agent
    is woken late and sees `## code` already at round-2, it still
    produces its round-2 body because the spec count says so.
    """
    spec = section_body(content, "spec")
    return sum(1 for ln in spec.splitlines() if ln.lstrip().startswith("- "))


def get_response(role: str, content: str, round_idx: int) -> str:
    use_fake = USE_FAKE or not shutil.which("claude")
    if not use_fake:
        try:
            return call_claude(role, content)
        except Exception as e:
            print(f"  ✗ claude failed: {e}; using fake", flush=True)
    bodies = FAKE_BODIES[role]
    # In fake mode, derive the round index from the doc's CURRENT state
    # (spec bullet count) rather than from the agent's own iteration
    # counter. This is robust to races where a downstream agent wakes
    # late and never sees an intermediate state of its dependency.
    state_round = max(0, _spec_bullet_count(content) - 1)
    return bodies[min(state_round, len(bodies) - 1)]


# -- main loop --------------------------------------------------------------

def main() -> int:
    if len(sys.argv) < 2:
        sys.stderr.write(
            "usage: bg-claude.py <" + "|".join(DEPENDENCIES) + ">\n"
        )
        return 2
    role = sys.argv[1].lower()
    if role not in DEPENDENCIES:
        sys.stderr.write(f"unknown role {role}\n")
        return 2

    dep = DEPENDENCIES[role]
    print(f"agent:{role}")
    print("─" * 28, flush=True)
    print(f"  reads:  ## {dep}", flush=True)
    print(f"  writes: ## {role}", flush=True)

    last_dep_hash = ""
    rounds_done = 0
    consecutive_errors = 0

    while rounds_done < MAX_ROUNDS:
        try:
            meta = json.loads(
                subprocess.check_output(
                    ["cotype", "open", "task.md", "--json"], timeout=10,
                )
            )
        except Exception as e:
            print(f"  ✗ open: {e}", flush=True)
            time.sleep(POLL_INTERVAL)
            continue

        content = Path(meta["base_path"]).read_text()

        # Wait for the dependency section to be filled in.
        if is_placeholder(section_body(content, dep)):
            time.sleep(POLL_INTERVAL)
            continue

        cur_dep_hash = section_hash(content, dep)
        if cur_dep_hash == last_dep_hash:
            time.sleep(POLL_INTERVAL)
            continue

        round_idx = rounds_done
        print(f"  · regenerating (round {round_idx + 1}, ## {dep} changed)",
              flush=True)
        new_body = get_response(role, content, round_idx)
        proposed = replace_section_body(content, role, new_body)

        try:
            r = subprocess.run(
                [
                    "cotype", "save", "task.md",
                    "--base-sha", meta["base_sha"],
                    "--actor", f"agent:{role}",
                    "--json",
                ],
                input=proposed.encode(),
                capture_output=True, check=False, timeout=10,
            )
            result = json.loads(r.stdout)
        except Exception as e:
            print(f"  ✗ save: {e}", flush=True)
            time.sleep(POLL_INTERVAL)
            continue

        status = result.get("status", "??")
        if status == "saved":
            mode = result.get("mode", "??")
            print(f"  {ICONS.get(mode, '?')}  save: {mode} (round {round_idx + 1})",
                  flush=True)
            last_dep_hash = cur_dep_hash
            rounds_done += 1
            consecutive_errors = 0
        elif status == "conflict":
            print(f"  ✗  conflict {result.get('conflict_id', '?')[:8]}…  "
                  "(retrying next poll)", flush=True)
            consecutive_errors += 1
        elif status == "error":
            err = result.get("error", "??")
            print(f"  ✗  {err}: {result.get('message', '')}", flush=True)
            consecutive_errors += 1
            if err == "ConflictPending":
                time.sleep(POLL_INTERVAL * 2)
        else:
            print(f"  ?  unexpected: {result}", flush=True)
            consecutive_errors += 1

        if consecutive_errors >= 5:
            print("  ✗ too many errors, idling", flush=True)
            break

        time.sleep(POLL_INTERVAL)

    while True:
        time.sleep(60)


if __name__ == "__main__":
    sys.exit(main())
