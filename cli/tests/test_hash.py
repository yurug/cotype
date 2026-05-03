"""Tests for stile.hash."""
from __future__ import annotations

import hashlib
import os
import random

import pytest

from stile.errors import UnknownBase
from stile.hash import HASH_RE, hash_bytes, hex_part


def test_P5_hash_byte_exact_empty():
    # H(b"") is the well-known SHA-256 of the empty string.
    assert hash_bytes(b"") == "sha256:" + hashlib.sha256(b"").hexdigest()


def test_P5_hash_byte_exact_random():
    rng = random.Random(0)
    for _ in range(50):
        n = rng.randint(0, 8192)
        b = os.urandom(n)
        assert hash_bytes(b) == "sha256:" + hashlib.sha256(b).hexdigest()


def test_P5_hash_preserves_no_normalisation():
    # Each input is hashed verbatim -- no CRLF/LF coercion, no BOM stripping,
    # no trailing-newline insertion.
    cases = [b"abc", b"abc\n", b"abc\r\n", b"\xef\xbb\xbfBOM", b"line1\nline2"]
    for b in cases:
        assert hash_bytes(b) == "sha256:" + hashlib.sha256(b).hexdigest()


def test_HASH_RE_matches_canonical():
    assert HASH_RE.match("sha256:" + "0" * 64)
    assert HASH_RE.match("sha256:" + "f" * 64)


def test_HASH_RE_rejects_uppercase_hex():
    assert not HASH_RE.match("sha256:" + "F" * 64)


def test_hex_part_valid():
    h = "sha256:" + "a" * 64
    assert hex_part(h) == "a" * 64


def test_hex_part_rejects_malformed():
    for bad in [
        "",
        "sha256:",
        "sha256:abcd",
        "sha1:" + "a" * 64,
        "SHA256:" + "a" * 64,
        "sha256:" + "Z" * 64,
        "sha256:" + "a" * 63,
        "sha256:" + "a" * 65,
    ]:
        with pytest.raises(UnknownBase):
            hex_part(bad)
