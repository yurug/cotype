"""Tests for stile.lock."""
from __future__ import annotations

import threading
import time
from pathlib import Path

from stile.lock import sidecar_lock
from stile.store import ensure_layout


def test_P6_lock_serialises_threads(tmp_path: Path):
    sidecar = tmp_path / ".file.txt.stile"
    ensure_layout(sidecar)
    timeline: list[tuple[str, str]] = []

    def worker(label: str, hold: float):
        with sidecar_lock(sidecar):
            timeline.append(("acq", label))
            time.sleep(hold)
            timeline.append(("rel", label))

    t1 = threading.Thread(target=worker, args=("A", 0.05))
    t2 = threading.Thread(target=worker, args=("B", 0.05))
    t1.start()
    time.sleep(0.01)  # ensure t1 acquires before t2 runs
    t2.start()
    t1.join()
    t2.join()

    # Acquisitions must not interleave -- one full hold then the other.
    assert timeline in (
        [("acq", "A"), ("rel", "A"), ("acq", "B"), ("rel", "B")],
        [("acq", "B"), ("rel", "B"), ("acq", "A"), ("rel", "A")],
    ), timeline


def test_lock_released_after_exception(tmp_path: Path):
    sidecar = tmp_path / ".file.txt.stile"
    ensure_layout(sidecar)
    try:
        with sidecar_lock(sidecar):
            raise RuntimeError("boom")
    except RuntimeError:
        pass
    # If the lock is still held, this would deadlock; the test would hang
    # rather than fail. We use a short window to demonstrate the lock is
    # immediately re-acquirable.
    acquired = []

    def w():
        with sidecar_lock(sidecar):
            acquired.append(True)

    t = threading.Thread(target=w)
    t.start()
    t.join(timeout=2.0)
    assert acquired == [True]
