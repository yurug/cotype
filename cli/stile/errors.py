"""Error hierarchy and stable error names.

Spec refs: kb/spec/error-taxonomy.md, kb/conventions/error-handling.md
The names and exit codes on each subclass are part of the integration contract.
Renaming any of them is a breaking change.
"""
from __future__ import annotations

from typing import ClassVar


class StileError(Exception):
    """Base for every stile-raised error.

    Each subclass carries:
        name      -- the stable string used in JSON `error` payloads.
        exit_code -- the process exit code per kb/spec/error-taxonomy.md.

    The default values here are deliberately the IO defaults; every concrete
    subclass overrides both.
    """

    name: ClassVar[str] = "StileError"
    exit_code: ClassVar[int] = 6


class UsageError(StileError):
    name = "UsageError"
    exit_code = 2


class UnsupportedFile(StileError):
    name = "UnsupportedFile"
    exit_code = 3


class UnmanagedFile(StileError):
    name = "UnmanagedFile"
    exit_code = 3


class CorruptSidecar(StileError):
    name = "CorruptSidecar"
    exit_code = 3


class UnknownBase(StileError):
    name = "UnknownBase"
    exit_code = 4


class ConflictPending(StileError):
    name = "ConflictPending"
    exit_code = 5


class ConflictIdMismatch(StileError):
    name = "ConflictIdMismatch"
    exit_code = 2


class IoError(StileError):
    name = "IoError"
    exit_code = 6


class MergeToolError(StileError):
    name = "MergeToolError"
    exit_code = 7


class InvalidUtf8(StileError):
    name = "InvalidUtf8"
    exit_code = 3
