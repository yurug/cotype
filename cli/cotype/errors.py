"""Error hierarchy and stable error names.

Spec refs: kb/spec/error-taxonomy.md, kb/conventions/error-handling.md
The names and exit codes on each subclass are part of the integration contract.
Renaming any of them is a breaking change.
"""
from __future__ import annotations

from typing import ClassVar


class CotypeError(Exception):
    """Base for every cotype-raised error.

    Each subclass carries:
        name      -- the stable string used in JSON `error` payloads.
        exit_code -- the process exit code per kb/spec/error-taxonomy.md.

    The default values here are deliberately the IO defaults; every concrete
    subclass overrides both.
    """

    name: ClassVar[str] = "CotypeError"
    exit_code: ClassVar[int] = 6


class UsageError(CotypeError):
    name = "UsageError"
    exit_code = 2


class UnsupportedFile(CotypeError):
    name = "UnsupportedFile"
    exit_code = 3


class UnmanagedFile(CotypeError):
    name = "UnmanagedFile"
    exit_code = 3


class CorruptSidecar(CotypeError):
    name = "CorruptSidecar"
    exit_code = 3


class UnknownBase(CotypeError):
    name = "UnknownBase"
    exit_code = 4


class ConflictPending(CotypeError):
    name = "ConflictPending"
    exit_code = 5


class IoError(CotypeError):
    name = "IoError"
    exit_code = 6


class MergeToolError(CotypeError):
    name = "MergeToolError"
    exit_code = 7


class InvalidUtf8(CotypeError):
    name = "InvalidUtf8"
    exit_code = 3
