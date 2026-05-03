"""T10 -- atomic visibility under concurrent reader.

A reader hashing FILE in a tight loop while a writer alternates between two
contents must always observe the hash of one of the complete versions; never
a torn or empty read.
"""
from __future__ import annotations

import threading
from pathlib import Path

from stile.commands.init import cmd_init
from stile.commands.open_ import cmd_open
from stile.commands.save import cmd_save
from stile.hash import hash_bytes


def test_T10_P2_atomic_visibility(tmp_path: Path):
    f = tmp_path / "big.txt"
    A = b"A" * 65536 + b"\n"
    B = b"B" * 65536 + b"\n"
    f.write_bytes(A)
    cmd_init(str(f))
    valid = {hash_bytes(A), hash_bytes(B)}

    stop = threading.Event()
    observations: list[str] = []
    errors: list[tuple[str, BaseException]] = []

    def reader():
        # Read directly; do NOT hold any stile lock. The point is to verify
        # external readers (build systems, watchers, cat) see whole files.
        while not stop.is_set():
            try:
                b = f.read_bytes()
            except FileNotFoundError as e:
                errors.append(("read", e))
                continue
            if not b:
                errors.append(("empty", RuntimeError("empty read")))
                continue
            observations.append(hash_bytes(b))

    def writer():
        toggle = True
        for _ in range(40):
            if stop.is_set():
                break
            try:
                op = cmd_open(str(f))
                payload = B if toggle else A
                cmd_save(str(f), op["base_sha"], "writer", payload)
                toggle = not toggle
            except Exception as e:  # any unexpected error fails the test
                errors.append(("write", e))
                break

    rt = threading.Thread(target=reader)
    wt = threading.Thread(target=writer)
    rt.start()
    wt.start()
    wt.join()
    stop.set()
    rt.join(timeout=5)

    assert not errors, errors
    bad = [h for h in observations if h not in valid]
    assert not bad, f"unexpected hashes: {bad[:3]} (of {len(observations)})"
    # Confirm the test actually exercised both states (not just A or just B).
    assert len(set(observations)) >= 2, observations[:5]
