"""SHA-256 content hashing.

H(b) = "sha256:" ++ lowercase_hex(SHA256(b))

Spec refs: kb/spec/data-model.md#hash
Properties enforced: P5 (byte-exact: bytes are hashed verbatim, with no
normalisation of line endings, BOMs, trailing newlines, or anything else).
"""
from __future__ import annotations

import hashlib
import re

from cotype.errors import UnknownBase

# Canonical hash form; case-sensitive. The hex is required to be lowercase.
HASH_RE = re.compile(r"^sha256:[0-9a-f]{64}$")


def hash_bytes(b: bytes) -> str:
    """Return the canonical 'sha256:<hex>' hash of `b`.

    The bytes are hashed verbatim (P5). The caller MUST pass the bytes exactly
    as read from disk -- no decode/re-encode round-trip.
    """
    return "sha256:" + hashlib.sha256(b).hexdigest()


def hex_part(hash_str: str) -> str:
    """Return the 64-char hex suffix of `hash_str`, after validating its form.

    Raises UnknownBase on any malformation. Using UnknownBase (not UsageError)
    matches the user-visible cause: a syntactically wrong --base-sha can never
    name a real base, so "no such base" is the right surface error.
    """
    if not HASH_RE.match(hash_str):
        raise UnknownBase(f"hash {hash_str!r} is not a valid sha256:<hex64>")
    return hash_str[len("sha256:"):]
