#!/usr/bin/env python3
"""Polling agent for the multi-section collaborative-doc demo.

Each agent OWNS one Markdown section in `task.md` and READS another.
On every poll cycle the agent computes the SHA-256 of its dependency
section; if it differs from what the agent last reacted to, the agent
regenerates the BODY of its own section and submits the whole document
to `stile save`. Different actors edit different sections, so concurrent
saves are disjoint diffs that stile's `diff3 -m` merges cleanly -- the
first save lands `direct`, subsequent ones land `merged`.

Roles:

  engineer   reads `## requirements`   writes `## engineer`
  tester     reads `## engineer`       writes `## tester`
  marketer   reads `## engineer`       writes `## marketer`

Real LLM responses come from the `claude` CLI when it is on PATH;
otherwise (and when STILE_DEMO_FAKE_CLAUDE=1) the agent uses canned
per-round bodies indexed by how many rounds it has performed.

Usage: bg-claude.py <engineer|tester|marketer>
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
USE_FAKE = bool(os.environ.get("STILE_DEMO_FAKE_CLAUDE"))
CLAUDE_TIMEOUT = float(os.environ.get("STILE_DEMO_CLAUDE_TIMEOUT", "60"))

# Each role's input section is the section it reacts to.
DEPENDENCIES = {
    "engineer": "requirements",
    "tester":   "engineer",
    "marketer": "engineer",
}

ICONS = {"direct": "✓", "merged": "⚡", "noop": "·", "conflict": "✗"}

# Canned bodies per role per round (used in fake mode and as a safety
# net when the `claude` CLI errors out). Round 0 is the response to the
# initial seed; later rounds reflect successive user-driven changes to
# the requirements (tantrum-proof, then $5 budget).
FAKE_BODIES = {
    "engineer": [
        "PVC pipe body, paper nose cone.\n"
        "Estes B6-4 motor, 30 cm length, 200 g.\n"
        "Three balsa fins, hot-glued.",

        "Foam-over-PVC nose cone (impact-rated).\n"
        "Reinforced fin attachment with epoxy.\n"
        "Same B6-4 motor, 220 g.",

        "Cardboard tube body, electrical-tape fins.\n"
        "Estes A8-3 motor (single-use, $4).\n"
        "Foam nose, 120 g, no recovery -- glide.",
    ],
    "tester": [
        "Drop test from 1 m.\n"
        "Outdoor ignition, 50 m safety zone.\n"
        "Verify parachute deploys at apogee.",

        "Add pendulum wall-impact test (foam-on-foam).\n"
        "5 m simulated child-throw.\n"
        "Plus the existing 1 m drop test.",

        "Drop the wall-impact test (out of budget).\n"
        "Single outdoor launch as acceptance.\n"
        "Recovery confirmed visually only.",
    ],
    "marketer": [
        "POCKET ROCKET — fits where physics doesn't.",
        "Still flying after the kid's tantrum.",
        "Less than a burrito. More fun than a kite.",
    ],
}


# -- doc parsing / rewriting -------------------------------------------------

_HEADER_RE = re.compile(r"^## (.+?)\s*$", re.MULTILINE)


def parse_sections(content: str) -> tuple[str, list[tuple[str, str]]]:
    """Return (preamble, [(name, body), ...]) preserving document order."""
    matches = list(_HEADER_RE.finditer(content))
    if not matches:
        return content, []
    preamble = content[: matches[0].start()]
    sections: list[tuple[str, str]] = []
    for i, m in enumerate(matches):
        name = m.group(1).strip()
        body_start = m.end() + 1  # +1 for newline after header
        body_end = matches[i + 1].start() if i + 1 < len(matches) else len(content)
        body = content[body_start:body_end]
        sections.append((name, body))
    return preamble, sections


def render_doc(preamble: str, sections: list[tuple[str, str]]) -> str:
    out = [preamble]
    for name, body in sections:
        out.append(f"## {name}\n")
        out.append(body)
    return "".join(out)


def replace_section_body(content: str, target: str, new_body: str) -> str:
    """Return `content` with the body of `## target` replaced by `new_body`.

    `new_body` is normalised to end with a single blank line, so that the
    next `## ` header sits on a line of its own and diff3 has at least one
    unchanged line of context between sections.
    """
    preamble, sections = parse_sections(content)
    new_body = new_body.rstrip("\n") + "\n\n"
    for i, (name, _body) in enumerate(sections):
        if name == target:
            sections[i] = (name, new_body)
            break
    return render_doc(preamble, sections)


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

    The seed file uses bodies like `(no design yet -- waiting on
    requirements)`. Downstream agents must wait until their dependency
    section is actually filled in -- otherwise they'd react to the
    placeholder text and burn their round-0 canned body on it."""
    stripped = body.strip()
    return not stripped or stripped.startswith("(no ")


# -- response generation ----------------------------------------------------

def call_claude(role: str, content: str) -> str:
    dep = DEPENDENCIES[role]
    role_hint = {
        "engineer": "Propose a concrete design (parts, dimensions, mass).",
        "tester":   "Propose a test plan (what to verify, how).",
        "marketer": "Write a single-line tagline.",
    }[role]
    prompt = (
        f"You are agent:{role} working in a shared Markdown document called "
        "`task.md` alongside a human user. The file is managed by `stile`. "
        f"Your job: write the BODY of the `## {role}` section, reacting to "
        f"the current `## {dep}` section. Be concise (2-5 short lines). "
        "Output ONLY the body (no header, no codefences, no preamble, no "
        "closing remarks). The project is a tiny backpack-sized rocket; "
        f"stay in your role: {role_hint}\n\n"
        f"<file>\n{content}\n</file>\n"
    )
    r = subprocess.run(
        ["claude", "--print", "-p", prompt],
        capture_output=True, text=True, check=True, timeout=CLAUDE_TIMEOUT,
    )
    text = r.stdout.strip()
    if text.startswith("```"):
        lines = text.splitlines()
        if lines[0].startswith("```"):
            lines = lines[1:]
        if lines and lines[-1].startswith("```"):
            lines = lines[:-1]
        text = "\n".join(lines).strip()
    return text


def get_response(role: str, content: str, round_idx: int) -> str:
    use_fake = USE_FAKE or not shutil.which("claude")
    if not use_fake:
        try:
            return call_claude(role, content)
        except Exception as e:
            print(f"  ✗ claude failed: {e}; using fake", flush=True)
    bodies = FAKE_BODIES[role]
    return bodies[min(round_idx, len(bodies) - 1)]


# -- main loop --------------------------------------------------------------

def main() -> int:
    if len(sys.argv) < 2:
        sys.stderr.write("usage: bg-claude.py <engineer|tester|marketer>\n")
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
                    ["stile", "open", "task.md", "--json"], timeout=10,
                )
            )
        except Exception as e:
            print(f"  ✗ open: {e}", flush=True)
            time.sleep(POLL_INTERVAL)
            continue

        content = Path(meta["base_path"]).read_text()

        # Wait for the dependency section to be filled in. Without this
        # gate, tester / marketer would treat the seed's "(no design yet)"
        # placeholder as round-0 input and waste their first canned body.
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
                    "stile", "save", "task.md",
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
                # Someone else's conflict; we wait it out.
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
