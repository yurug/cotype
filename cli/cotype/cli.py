"""CLI dispatch and JSON envelope -- the thinnest layer cotype has.

Where this module sits in the architecture
==========================================

Three concentric rings:

    cli.py              -- argparse, dispatch, JSON envelope.
    commands/*.py       -- one file per subcommand. Each `cmd_*'
                           function takes parsed args, returns a dict
                           (the success envelope), or raises a
                           `CotypeError'.
    everything else     -- the actual mechanism: hashing, locking,
                           atomic writes, merge, store.

This file is intentionally a "boring sandwich": parse, route, format
output. No business logic lives here. If you find yourself wanting
to add an `if/else' that decides what cotype DOES, that's a smell --
push it down into `commands/' (or further, into `merge', `store',
etc.).

The JSON envelope as the primary contract
=========================================

`--json' on every command (except `cat-base', which would mix
metadata with the bytes payload) emits a one-shot JSON document on
stdout. Errors take the same stream:

    {"status": "error", "error": "<StableName>", "message": "..."}

Human-readable strings (the `else' branch in `emit_success') are
convenience for terminal use; they are NOT a contract. Tools should
parse `--json'.

Exit codes are part of the contract
===================================

In addition to the JSON envelope, the process exit code carries
classification information for shell pipelines. The mapping comes
from the `exit_code' attribute on each `CotypeError' subclass; the
one special case is `status: "conflict"' on a successful `cotype
save', which exits with code 1 (a non-error result that callers
typically want to detect). See `main()' near the bottom.

The `cat-base' special case
===========================

`cat-base' is the one subcommand that doesn't go through the JSON
envelope. Its success path streams raw bytes to stdout (so it
composes in shell pipelines like `cat-base | my-agent | save'); its
error path takes the normal stderr route. There's no `--json'
because mixing JSON metadata with the bytes on the same stream would
be unparseable.

Spec refs: kb/spec/api-contracts.md, kb/spec/error-taxonomy.md
"""
from __future__ import annotations

import argparse
import json as json_mod
import sys
from typing import Optional, Sequence

from cotype import __version__
from cotype.commands.catbase import cmd_catbase
from cotype.commands.init import cmd_init
from cotype.commands.open_ import cmd_open
from cotype.commands.resolve import cmd_resolve
from cotype.commands.save import cmd_save
from cotype.commands.status import cmd_status
from cotype.errors import IoError, CotypeError, UsageError


_TOP_DESCRIPTION = """\
cotype: a tiny CLI that lets a user and one or more processes (typically AI
agents) edit the SAME text file concurrently without losing anyone's edits.
Each save goes through a 3-way merge against the actor's captured base;
overlapping edits surface as explicit conflicts (diff3 markers in the file)
that the user resolves inline.
"""

_TOP_EPILOG = """\
PROTOCOL (every actor follows the same flow -- there is no privileged path):

    meta=$(cotype open FILE --json)
    base_sha=$(printf '%s' "$meta" | jq -r .base_sha)
    base_path=$(printf '%s' "$meta" | jq -r .base_path)
    # IMPORTANT: read the file content from base_path, NOT by re-reading FILE.
    # A separate read is racy -- another writer could land between open and
    # your read, and cotype would not detect the staleness.
    new_content=$(my-edit < "$base_path")
    printf '%s' "$new_content" | cotype save FILE \\
        --base-sha "$base_sha" --actor my-name --json

OUTCOMES of `cotype save` (the "mode" field, or `status` on failure):

    direct   -- base matched current; proposed written atomically.
    merged   -- 3-way merge produced a clean result; merged content written.
    noop     -- proposed equals current; nothing to do.
    conflict -- overlapping edits; FILE rewritten with diff3 markers
                (`<<<<<<<` / `=======` / `>>>>>>>`); further saves rejected
                with ConflictPending until the user edits the markers out
                and runs `cotype resolve FILE`.

MINIMIZING CONFLICTS (multi-actor flows):

    cotype's merge is line-based (POSIX diff3) and groups edits within
    the same hunk -- adjacent-but-independent line edits can collide
    even when neither side overwrites the other's bytes. Two cheap
    tricks keep concurrent saves clean:

    1. Pad boundaries.  diff3 needs ~2 unchanged lines between two
       edit zones to treat them as separate hunks. Insert blank lines
       or a stable sentinel comment between regions different actors
       own. The bigger the unchanged anchor, the smaller the chance
       of spurious conflicts.

    2. Splice structurally in your harness, not at the byte level.
       Parse the file into regions (Markdown sections, top-level
       defs, JSON keys) and rewrite ONLY your own region's bytes.
       Other regions then come from `base_path` byte-exact, so two
       actors editing two different regions cannot conflict by
       construction. `examples/headless-agents.sh` is the reference
       recipe for the Markdown-section case.

INTEGRATION:

    --json on every command except `cat-base` emits a parseable envelope on
    stdout; errors emit `{"status":"error","error":"<Name>","message":"..."}`.
    Human-readable output is convenience, not contract.

    Exit codes: 0 success, 1 conflict, 2 usage, 3 unmanaged/corrupt/utf-8,
    4 unknown base, 5 pending conflict, 6 i/o, 7 merge tool error.

Full spec, properties, and design notes:
    https://github.com/yurug/cotype/tree/main/kb
"""

_INIT_DESC = """\
First-time setup: create the sidecar directory `.<basename>.cotype/` next
to FILE and capture the current contents as the very first base snapshot.
Idempotent -- running `init` on an already-managed file is a no-op.

After this, every subsequent edit must go through `cotype open` followed
by `cotype save`, never a direct write.
"""

_OPEN_DESC = """\
Capture a fresh base snapshot of FILE so you can edit against a known
version. Returns `base_sha` and a `base_path` to read the bytes from.

CRITICAL: load your editor buffer (or your generator's input) from
`base_path`, not by re-reading FILE itself. A separate read is racy --
another actor could land a save between `open` and your read, and the
stale-base check would not catch it.

If FILE has a pending conflict, `open` still succeeds (so a viewer can
load the marker-laden content) but `conflicted: true` is set.
"""

_SAVE_DESC = """\
Submit proposed bytes (read from stdin) as a new version of FILE, against
the `base_sha` returned by your own most recent `open`. cotype decides per
save whether it's a `direct` write, a `merged` 3-way result, a `noop`
(proposed already on disk), or a `conflict`.

Use --json to get the structured envelope. The `--actor` label is opaque;
it is recorded in conflict metadata only and never affects semantics.
"""

_STATUS_DESC = """\
Report the current state of FILE: `unmanaged` (no sidecar), `clean`
(managed, no pending conflict), or `conflicted` (a previous save left
diff3 markers in FILE; saves are blocked until `cotype resolve` runs).

Read-only and side-effect-free; safe to poll.
"""

_RESOLVE_DESC = """\
Clear a pending conflict by accepting the current contents of FILE.

After `cotype save` produced a `conflict`, FILE was rewritten with diff3
markers and the sidecar marks the conflict as pending. The user opens
FILE in their editor, removes the `<<<<<<<` / `=======` / `>>>>>>>`
blocks, saves the buffer, and runs `cotype resolve FILE`. cotype refuses
if any markers remain.

Reads no stdin; the resolution is whatever bytes are in FILE on disk.
"""

_CATBASE_DESC = """\
Write the raw bytes of a base snapshot to stdout, for use in shell
pipelines that need to read a specific base without going through `open`
(which would create a new snapshot and update `last_known_sha`).

With no `--base-sha`, returns the most recently captured base.
Output is bytes; this command intentionally has no `--json` flag.
"""


def build_parser() -> argparse.ArgumentParser:
    p = argparse.ArgumentParser(
        prog="cotype",
        description=_TOP_DESCRIPTION,
        epilog=_TOP_EPILOG,
        formatter_class=argparse.RawDescriptionHelpFormatter,
    )
    p.add_argument("--version", action="version", version=f"cotype {__version__}")
    sub = p.add_subparsers(
        dest="command",
        required=True,
        title="commands",
        metavar="COMMAND",
    )

    sub_kwargs = {"formatter_class": argparse.RawDescriptionHelpFormatter}

    p_init = sub.add_parser(
        "init",
        help="first-time setup: create sidecar + capture initial base",
        description=_INIT_DESC,
        **sub_kwargs,
    )
    p_init.add_argument("file")
    p_init.add_argument("--json", action="store_true")

    p_open = sub.add_parser(
        "open",
        help="capture a fresh base snapshot before editing",
        description=_OPEN_DESC,
        **sub_kwargs,
    )
    p_open.add_argument("file")
    p_open.add_argument("--json", action="store_true")

    p_save = sub.add_parser(
        "save",
        help="save proposed content (stdin) against --base-sha",
        description=_SAVE_DESC,
        **sub_kwargs,
    )
    p_save.add_argument("file")
    p_save.add_argument(
        "--base-sha",
        required=True,
        help="the base_sha returned by your own most recent `cotype open`",
    )
    p_save.add_argument(
        "--actor",
        default="unknown",
        help='free-form label (e.g. "emacs", "agent:reviewer"); recorded in conflict metadata',
    )
    p_save.add_argument("--json", action="store_true")

    p_status = sub.add_parser(
        "status",
        help="report state: unmanaged | clean | conflicted",
        description=_STATUS_DESC,
        **sub_kwargs,
    )
    p_status.add_argument("file")
    p_status.add_argument("--json", action="store_true")

    p_resolve = sub.add_parser(
        "resolve",
        help="clear a pending conflict by accepting FILE on disk",
        description=_RESOLVE_DESC,
        **sub_kwargs,
    )
    p_resolve.add_argument("file")
    p_resolve.add_argument("--actor", default="unknown")
    p_resolve.add_argument("--json", action="store_true")

    p_catbase = sub.add_parser(
        "cat-base",
        help="write a base snapshot's bytes to stdout (no --json)",
        description=_CATBASE_DESC,
        **sub_kwargs,
    )
    p_catbase.add_argument("file")
    p_catbase.add_argument(
        "--base-sha",
        default=None,
        help="which base to read; defaults to state.last_known_sha",
    )

    return p


def emit_success(payload: dict, *, json_mode: bool) -> None:
    """Write a success payload to stdout in either JSON or human form.

    `json_mode' True   -> pretty-printed JSON object on stdout, the
                          parseable contract for tools.
    `json_mode' False  -> a one-line human summary, convenience only.
                          Format is intentionally not stable across
                          versions; tools must use --json.
    """
    if json_mode:
        sys.stdout.write(json_mod.dumps(payload, indent=2) + "\n")
        return
    # Human-readable fallback. Branches per `status' field. Order
    # matches the per-subcommand response shape documented in
    # kb/spec/api-contracts.md.
    s = payload.get("status")
    if s == "saved":
        sys.stdout.write(f"saved ({payload['mode']}) {payload['sha']}\n")
    elif s == "conflict":
        sys.stdout.write(
            f"conflict {payload['conflict_id']} (see {payload['conflict_path']})\n"
        )
    elif s == "ok":
        # `init' returns `sha'; `open' returns `base_sha'. Same idea
        # at the human-line level, so collapse them.
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
        # Defensive: an unexpected payload (e.g., a future status we
        # don't have a human pretty-printer for) still gets shown
        # rather than silently dropped. Falls back to raw JSON dump.
        sys.stdout.write(json_mod.dumps(payload) + "\n")


def emit_error(e: CotypeError, *, json_mode: bool) -> None:
    """Write a CotypeError to the right stream + format.

    JSON mode: error envelope on STDOUT (alongside successes), so
    `--json'-aware callers parse one stream regardless of outcome.

    Human mode: `error: <Name>: <message>' on STDERR, leaving stdout
    clean for the success-only happy path of shell pipelines.
    """
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
    """Top-level dispatcher: parse, route, emit, exit-code.

    The structure is the simplest possible "thick parser, thin
    main": argparse does all the validation up front; main()'s job
    is to call the right `cmd_*' function with the right args and
    classify the result.

    Why we wrap `OSError' at the bottom: the `commands/*' modules
    convert OS-level errors to `IoError' close to the source, but a
    handful of stdlib calls (e.g., `parser.parse_args' indirectly
    via argparse, or `sys.stdin.buffer.read' under odd terminal
    states) can still raise raw `OSError'. Catching it here gives
    those a clean exit-code path through the same `emit_error'
    formatter.
    """
    parser = build_parser()
    args = parser.parse_args(argv)
    json_mode = bool(getattr(args, "json", False))
    try:
        if args.command == "init":
            payload = cmd_init(args.file)
        elif args.command == "open":
            payload = cmd_open(args.file)
        elif args.command == "save":
            # `save' is the one command that consumes stdin: the
            # proposed bytes. Read the whole stream eagerly; cotype
            # files are typically small text files so the memory
            # cost is fine, and streaming half a save would
            # complicate the contract for very little benefit.
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
            # The one subcommand that bypasses the JSON envelope:
            # success streams raw bytes to stdout. Returning early
            # skips the `emit_success' / exit-code logic below.
            sys.stdout.buffer.write(cmd_catbase(args.file, args.base_sha))
            return 0
        else:  # pragma: no cover -- argparse already enforces required=True
            raise UsageError(f"unknown command: {args.command}")
        emit_success(payload, json_mode=json_mode)
        # `conflict' on save is a non-error RESULT, but it gets exit
        # code 1 because shell pipelines typically want to branch on
        # it (`cotype save FILE ... || handle_conflict').
        if payload.get("status") == "conflict":
            return 1
        return 0
    except CotypeError as e:
        emit_error(e, json_mode=json_mode)
        return e.exit_code
    except OSError as e:
        # Unwrap into IoError so the exit code and JSON envelope
        # match what callers expect (see emit_error).
        emit_error(IoError(str(e)), json_mode=json_mode)
        return 6
