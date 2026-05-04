"""CLI dispatch and JSON envelope.

Spec refs: kb/spec/api-contracts.md, kb/spec/error-taxonomy.md
"""
from __future__ import annotations

import argparse
import json as json_mod
import sys
from typing import Optional, Sequence

from stile import __version__
from stile.commands.catbase import cmd_catbase
from stile.commands.init import cmd_init
from stile.commands.open_ import cmd_open
from stile.commands.resolve import cmd_resolve
from stile.commands.save import cmd_save
from stile.commands.status import cmd_status
from stile.errors import IoError, StileError, UsageError


def build_parser() -> argparse.ArgumentParser:
    p = argparse.ArgumentParser(
        prog="stile",
        description="Universal safe-save for concurrent text files.",
    )
    p.add_argument("--version", action="version", version=f"stile {__version__}")
    sub = p.add_subparsers(dest="command", required=True)

    p_init = sub.add_parser("init", help="initialise the sidecar for FILE")
    p_init.add_argument("file")
    p_init.add_argument("--json", action="store_true")

    p_open = sub.add_parser("open", help="capture a base snapshot of FILE")
    p_open.add_argument("file")
    p_open.add_argument("--json", action="store_true")

    p_save = sub.add_parser("save", help="save proposed content (stdin) for FILE")
    p_save.add_argument("file")
    p_save.add_argument("--base-sha", required=True)
    p_save.add_argument("--actor", default="unknown")
    p_save.add_argument("--json", action="store_true")

    p_status = sub.add_parser("status", help="report current state of FILE")
    p_status.add_argument("file")
    p_status.add_argument("--json", action="store_true")

    p_resolve = sub.add_parser(
        "resolve",
        help=(
            "clear a pending conflict by accepting FILE (after the user "
            "has edited out the conflict markers)"
        ),
    )
    p_resolve.add_argument("file")
    p_resolve.add_argument("--actor", default="unknown")
    p_resolve.add_argument("--json", action="store_true")

    # cat-base writes raw bytes; no --json flag (would mix with stdout body).
    p_catbase = sub.add_parser(
        "cat-base",
        help="write a base snapshot's bytes to stdout (defaults to last known)",
    )
    p_catbase.add_argument("file")
    p_catbase.add_argument("--base-sha", default=None)

    return p


def emit_success(payload: dict, *, json_mode: bool) -> None:
    if json_mode:
        sys.stdout.write(json_mod.dumps(payload, indent=2) + "\n")
        return
    s = payload.get("status")
    if s == "saved":
        sys.stdout.write(f"saved ({payload['mode']}) {payload['sha']}\n")
    elif s == "conflict":
        sys.stdout.write(
            f"conflict {payload['conflict_id']} (see {payload['conflict_path']})\n"
        )
    elif s == "ok":
        # `init` returns sha; `open` returns base_sha.
        sha = payload.get("sha") or payload.get("base_sha", "")
        sys.stdout.write(f"ok {payload.get('file', '')} {sha}\n")
    elif s == "clean":
        sys.stdout.write(f"clean {payload['file']} {payload['current_sha']}\n")
    elif s == "conflicted":
        sys.stdout.write(
            f"conflicted {payload['file']} "
            f"(pending {payload['pending_conflict']['id']})\n"
        )
    elif s == "unmanaged":
        sys.stdout.write(f"unmanaged {payload['file']}\n")
    elif s == "resolved":
        sys.stdout.write(f"resolved {payload['file']} {payload['sha']}\n")
    else:
        # Defensive: any unexpected payload still gets shown rather than swallowed.
        sys.stdout.write(json_mod.dumps(payload) + "\n")


def emit_error(e: StileError, *, json_mode: bool) -> None:
    if json_mode:
        sys.stdout.write(
            json_mod.dumps(
                {"status": "error", "error": e.name, "message": str(e)},
                indent=2,
            )
            + "\n"
        )
    else:
        sys.stderr.write(f"error: {e.name}: {e}\n")


def main(argv: Optional[Sequence[str]] = None) -> int:
    parser = build_parser()
    args = parser.parse_args(argv)
    json_mode = bool(getattr(args, "json", False))
    try:
        if args.command == "init":
            payload = cmd_init(args.file)
        elif args.command == "open":
            payload = cmd_open(args.file)
        elif args.command == "save":
            payload = cmd_save(
                args.file,
                args.base_sha,
                args.actor,
                sys.stdin.buffer.read(),
            )
        elif args.command == "status":
            payload = cmd_status(args.file)
        elif args.command == "resolve":
            payload = cmd_resolve(args.file, actor=args.actor)
        elif args.command == "cat-base":
            # cat-base bypasses the JSON envelope: success is raw bytes to
            # stdout, errors take the normal stderr path (no --json flag).
            sys.stdout.buffer.write(cmd_catbase(args.file, args.base_sha))
            return 0
        else:  # pragma: no cover -- argparse already enforces required=True
            raise UsageError(f"unknown command: {args.command}")
        emit_success(payload, json_mode=json_mode)
        # Conflict on save is a non-error result with exit code 1.
        if payload.get("status") == "conflict":
            return 1
        return 0
    except StileError as e:
        emit_error(e, json_mode=json_mode)
        return e.exit_code
    except OSError as e:
        emit_error(IoError(str(e)), json_mode=json_mode)
        return 6
