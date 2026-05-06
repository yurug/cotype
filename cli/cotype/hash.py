"""SHA-256 content hashing -- the byte-exact identity of a file's content.

Why this is so small and yet so load-bearing
============================================

The whole "safe save" protocol rests on one invariant:

    Two actors that read the same bytes from FILE will compute the
    same `base_sha`. Two actors that read different bytes will not.

That equality test is what `cotype save --base-sha SHA' uses to decide
"is the file unchanged since the caller's open?". If the hash function
*normalised* anything -- line endings, BOM, trailing newlines, decoded
and re-encoded UTF-8 -- two actors editing the same logical content
could disagree about whether the file changed, and the safe-save
guarantee falls apart in subtle ways.

So this module hashes raw bytes, verbatim, period. No I/O encoding
tricks, no normalisation. The functional-properties doc calls this
P5: "byte-exact". Tests in `tests/test_hash.py' nail it down with
files containing CRLF, missing trailing newlines, BOMs, and so on.

The canonical form
==================

A cotype hash is a 71-byte string:

    "sha256:" + 64 lowercase hex characters

The "sha256:" prefix is part of the value. We do this so the format
can carry algorithmic provenance forward if a future cotype ever
introduces a new hash function (call it `cotype_v2`); existing JSON
payloads carrying old hashes are still parseable, the prefix tells
the consumer which algorithm was used. Today, only "sha256:" is valid
and the regex below enforces that.

Why SHA-256 specifically: it's POSIX-stdlib (`hashlib.sha256` is
ubiquitous), collision-resistant in practice, and 32 bytes is a
comfortable storage size. SHA-1 would be smaller but its weakened
collision resistance is awkward as a primitive; BLAKE3 would be
faster but isn't in the stdlib.

Spec refs: kb/spec/data-model.md#hash
Properties enforced: P5 (byte-exact: bytes are hashed verbatim, with
no normalisation of line endings, BOMs, trailing newlines, or
anything else).
"""
from __future__ import annotations

import hashlib
import re

from cotype.errors import UnknownBase

# Canonical hash form. Case-sensitive: the hex MUST be lowercase, and
# the algorithm prefix is the literal "sha256:".
#
# Why we anchor (^...$) and reject anything fancier: this regex is the
# wire contract. A caller that submits a HASH outside this shape can
# never name a real base, and we want them to find that out via a
# clean `UnknownBase' error rather than have us silently go look in
# `bases/SHA256:abcdef.../' or some such.
HASH_RE = re.compile(r"^sha256:[0-9a-f]{64}$")


def hash_bytes(b: bytes) -> str:
    """Return the canonical 'sha256:<hex>' hash of `b`.

    The bytes are hashed verbatim. Callers must pass bytes EXACTLY
    as read from disk -- no `str.decode().encode()' round-trip, no
    "let me strip a trailing newline first". The latter would
    silently desynchronise actors' views of `base'.

    H(b)  in spec notation: "sha256:" ++ lowercase_hex(SHA256(b))
    """
    return "sha256:" + hashlib.sha256(b).hexdigest()


def hex_part(hash_str: str) -> str:
    """Return the 64-char hex suffix of `hash_str`, after validating its form.

    `hash_str' is what arrives on `--base-sha`. We use this both to
    check well-formedness (so a malformed flag fails fast and cleanly)
    and to extract the bare hex used as a filename component in
    `<sidecar>/bases/<hex>'.

    Why `UnknownBase' (not `UsageError'): the user's mental model is
    "I named a base; cotype can't find it". A syntactically wrong hash
    is the strongest possible "no such base" -- it could not, even in
    principle, name a real one. Reporting it as `UnknownBase' keeps
    the contract uniform: every "I can't find that base" failure has
    the same name, regardless of whether the cause was a typo in the
    flag or a sidecar that was wiped.
    """
    if not HASH_RE.match(hash_str):
        raise UnknownBase(f"hash {hash_str!r} is not a valid sha256:<hex64>")
    return hash_str[len("sha256:"):]
