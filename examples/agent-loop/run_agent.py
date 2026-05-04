#!/usr/bin/env python3
"""Drive an agent through the cotype open -> compute -> save loop, once.

Usage:
    run_agent.py FILE [--agent CMD] [--actor LABEL]

The agent is invoked as a subprocess:
    AGENT < base_bytes  > proposed_bytes

The default AGENT is `agent_mock.py` next to this script; override with
`--agent ./your_real_llm_driver.py` to plug in a real model.

Single-shot: this script does one pass and exits. To poll, wrap it:
    while true; do python3 run_agent.py task.md || break; sleep 30; done

Exit codes mirror `cotype save`:
    0  saved (direct | merged | noop)
    1  conflict (a forensic dump is at the printed path; resolve to continue)
    *  any other error from `cotype`, surfaced verbatim
"""
from __future__ import annotations

import argparse
import json
import shutil
import subprocess
import sys
from pathlib import Path


def run(args: list[str], stdin: bytes = b"") -> tuple[int, bytes, bytes]:
    p = subprocess.run(args, input=stdin, capture_output=True)
    return p.returncode, p.stdout, p.stderr


def main() -> int:
    p = argparse.ArgumentParser(description=__doc__.splitlines()[0])
    p.add_argument("file")
    p.add_argument(
        "--agent",
        default=str(Path(__file__).parent / "agent_mock.py"),
        help="path to an agent script that reads stdin and writes stdout",
    )
    p.add_argument("--actor", default="agent:mock")
    args = p.parse_args()

    if not shutil.which("cotype"):
        sys.stderr.write("error: cotype not on PATH (try: pip install -e cli/)\n")
        return 2

    # Auto-init the sidecar if absent so the script is idempotent.
    rc, out, _ = run(["cotype", "status", args.file, "--json"])
    if rc == 0 and json.loads(out).get("status") == "unmanaged":
        run(["cotype", "init", args.file, "--json"])

    # Capture a fresh base; refuse to act if a conflict is already pending.
    rc, out, err = run(["cotype", "open", args.file, "--json"])
    if rc != 0:
        sys.stderr.write(err.decode("utf-8", "replace") or out.decode("utf-8", "replace"))
        return rc
    meta = json.loads(out)
    if meta.get("conflicted"):
        pc = meta["pending_conflict"]
        sys.stderr.write(
            f"conflict pending: {pc['id']} (see {pc['path']}); "
            f"resolve before continuing\n"
        )
        return 1

    # Run the agent: stdin = base bytes, stdout = proposed bytes.
    base_bytes = Path(meta["base_path"]).read_bytes()
    rc, proposed, err = run([args.agent], stdin=base_bytes)
    if rc != 0:
        sys.stderr.write(
            f"agent failed (exit {rc}):\n"
            + err.decode("utf-8", "replace")
        )
        return rc

    # Save. Exit code 1 means conflict; surface the forensic path.
    rc, out, _ = run(
        [
            "cotype", "save", args.file,
            "--base-sha", meta["base_sha"],
            "--actor", args.actor,
            "--json",
        ],
        stdin=proposed,
    )
    try:
        result = json.loads(out)
    except json.JSONDecodeError:
        sys.stderr.write(out.decode("utf-8", "replace"))
        return rc if rc != 0 else 6

    status = result.get("status")
    if status == "saved":
        sys.stderr.write(f"save: {result['mode']}\n")
        return 0
    if status == "conflict":
        sys.stderr.write(
            f"conflict: {result['conflict_id']} (see {result['conflict_path']})\n"
        )
        return 1
    # Other error envelopes from cotype.
    sys.stderr.write(out.decode("utf-8", "replace"))
    return rc if rc != 0 else 6


if __name__ == "__main__":
    sys.exit(main())
