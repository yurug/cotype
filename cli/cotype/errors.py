"""Error hierarchy and stable error names.

Every cotype error inherits from `CotypeError`. Each subclass carries
two pieces of stable wire-contract information:

    name      -- the string that appears in JSON `error' payloads.
    exit_code -- the process exit code per kb/spec/error-taxonomy.md.

These names and codes are part of cotype's integration contract with
its callers (editor plugins, agent harnesses, shell scripts). Renaming
any of them, or shifting their exit codes, is a breaking change and
needs a major-version bump. New error names can be added without
breaking callers (they fall into the catch-all "anything not in the
table" handling), but existing ones are immutable.

Exit code conventions (echoing kb/spec/error-taxonomy.md):

    0  success                                          (not raised here)
    1  conflict                                         (not raised here -- it's
                                                         a non-error save outcome)
    2  usage error                                      (UsageError)
    3  unmanaged / corrupt / unsupported file           (UnsupportedFile,
                                                         UnmanagedFile,
                                                         CorruptSidecar,
                                                         InvalidUtf8)
    4  unknown base                                     (UnknownBase)
    5  pending conflict (cannot save yet)               (ConflictPending)
    6  generic I/O error                                (IoError)
    7  merge tool (diff3) error                         (MergeToolError)

The grouping at exit 3 is deliberate: every "the sidecar / file is in
a state cotype can't work with, but it isn't an i/o failure or a usage
mistake either" path lands there. A caller that distinguishes these
should branch on the JSON `error' field, not the exit code.

Where each subclass is raised in the source tree (a brief atlas):

    UsageError        argparse failures and the "no pending conflict
                      to resolve" / "markers still present" cases in
                      `commands/resolve.py'.
    UnsupportedFile   `paths.resolve_target' (target missing or not a
                      regular file).
    UnmanagedFile     `commands/{save,resolve,catbase}.py' when the
                      sidecar isn't there yet.
    CorruptSidecar    `store.read_state' when state.json is missing,
                      malformed, or has an unknown format_version.
    UnknownBase       `commands/save.py' (no `bases/<hex>' for the
                      caller's --base-sha) and `hash.hex_part' (the
                      --base-sha string itself is syntactically wrong).
    ConflictPending   `commands/save.py' when state.pending_conflict
                      is set -- ordinary saves are blocked until
                      `cotype resolve' clears it.
    IoError           Every `os.*' / file-handle-level failure that we
                      can't recover from. Last-resort bucket.
    MergeToolError    `merge.merge3' when `diff3' is missing or exits
                      with a status >= 2 (P10: tool failure must NEVER
                      be classified as a content conflict).
    InvalidUtf8       `commands/save.py' / `commands/resolve.py' when
                      bytes (current, proposed, or resolved) fail UTF-8
                      decoding. cotype refuses to manage non-UTF-8
                      because diff3's regex behaviour around mixed
                      encodings is undefined.

Spec refs: kb/spec/error-taxonomy.md, kb/conventions/error-handling.md
"""
from __future__ import annotations

from typing import ClassVar


class CotypeError(Exception):
    """Base class for every cotype-raised error.

    The `name' field is what appears in `--json' error payloads:

        { "status": "error", "error": "<name>", "message": "<detail>" }

    The `exit_code' is what `cli.main()' returns when a command raises
    this. The defaults below are deliberately the IoError defaults --
    every concrete subclass overrides both.
    """

    name: ClassVar[str] = "CotypeError"
    exit_code: ClassVar[int] = 6


class UsageError(CotypeError):
    """The caller asked for something cotype refuses on principle.

    Distinct from "argparse rejected your CLI flags" (argparse exits 2
    on its own before we see anything). Raised when the request was
    syntactically valid but semantically wrong: `cotype resolve' on a
    file with no pending conflict, or with diff3 markers still in the
    buffer, etc.
    """
    name = "UsageError"
    exit_code = 2


class UnsupportedFile(CotypeError):
    """The argument exists but isn't a regular text file we can manage.

    Directories, symlink loops, FIFOs, sockets, devices, and missing
    files all land here. cotype intentionally refuses anything but
    regular files because the safe-save dance assumes `os.replace`
    semantics that don't hold for special files.
    """
    name = "UnsupportedFile"
    exit_code = 3


class UnmanagedFile(CotypeError):
    """FILE has no sidecar yet; run `cotype init' first.

    Distinct from `UnsupportedFile': the file exists and is a plain
    text file, but cotype hasn't started managing it. `cotype init` is
    the way in.
    """
    name = "UnmanagedFile"
    exit_code = 3


class CorruptSidecar(CotypeError):
    """state.json is missing, malformed, or has an unknown
    format_version.

    Operationally rare -- usually only happens if someone hand-edited
    the sidecar, or a torn write somehow slipped past the atomic
    replace (which would itself be a bug). We raise instead of trying
    to recover because the right answer depends on the situation:
    sometimes you want to delete the sidecar and re-init, sometimes
    you want forensics. cotype declines to guess.
    """
    name = "CorruptSidecar"
    exit_code = 3


class UnknownBase(CotypeError):
    """The caller's --base-sha doesn't name any stored base snapshot.

    Two flavours:

      1. Syntactically wrong (not `sha256:<64 lowercase hex>'). Raised
         from `hash.hex_part' before we even look at the filesystem.
      2. Syntactically valid but no `bases/<hex>' file. Raised from
         `commands/save.py'.

    Both surface as the same error name because the caller can't
    proceed in either case.
    """
    name = "UnknownBase"
    exit_code = 4


class ConflictPending(CotypeError):
    """A previous save left a conflict that hasn't been resolved.

    Ordinary saves are refused with this until `cotype resolve' runs,
    so two unsynchronised actors can't pile new edits on top of one
    that's already in dispute. Inline diff3 markers in FILE are the
    user-visible indication.
    """
    name = "ConflictPending"
    exit_code = 5


class IoError(CotypeError):
    """Any underlying OS-level failure -- last-resort bucket.

    `errno`-flavoured failures (EIO, ENOSPC, EACCES, locking failures,
    ...) wrap to this. The message is the platform's OS error string;
    we don't try to interpret beyond that.
    """
    name = "IoError"
    exit_code = 6


class MergeToolError(CotypeError):
    """`diff3' is missing on PATH, or exited with status >= 2.

    P10 (functional properties): a *tool* failure to merge must NEVER
    be mis-classified as a *content* conflict. This is why the
    classification in `merge.merge3' branches strictly on diff3's
    exit code: 0 -> Clean, 1 -> Conflict, anything else -> raise.
    """
    name = "MergeToolError"
    exit_code = 7


class InvalidUtf8(CotypeError):
    """Some bytes failed UTF-8 decoding.

    cotype manages UTF-8 text files only. Refusing non-UTF-8 up-front
    is safer than passing arbitrary bytes through diff3 (whose
    behaviour on non-UTF-8 line splitting is implementation-defined).
    """
    name = "InvalidUtf8"
    exit_code = 3
