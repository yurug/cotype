"""Cross-cutting property tests not covered by a single command-test file.

Currently:
- P3 (sidecar is auxiliary -- FILE is still a normal file).
- P9 (protocol parity -- actor label does not affect outcome).
"""
from __future__ import annotations

import shutil
from pathlib import Path

from stile.commands.init import cmd_init
from stile.commands.open_ import cmd_open
from stile.commands.save import cmd_save
from stile.commands.status import cmd_status


def test_P3_sidecar_is_auxiliary(tmp_path: Path):
    """Deleting the sidecar must not corrupt FILE; it just returns to unmanaged."""
    f = tmp_path / "f.txt"
    f.write_text("payload\n")
    cmd_init(str(f))
    sidecar = tmp_path / ".f.txt.stile"
    assert sidecar.is_dir()

    shutil.rmtree(sidecar)

    # FILE is still readable, with original contents.
    assert f.read_text() == "payload\n"
    # Now the file is just "unmanaged" again.
    s = cmd_status(str(f))
    assert s["status"] == "unmanaged"


def test_P9_protocol_parity_actor_label_does_not_affect_outcome(tmp_path: Path):
    """Same input sequence with different actor labels yields the same outcome."""
    def run(actor: str, root: Path) -> dict:
        f = root / "f.txt"
        f.write_text("a\nb\nc\nd\ne\n")
        cmd_init(str(f))
        op = cmd_open(str(f))
        # Another actor changes line 2 between open and save.
        f.write_text("a\nB\nc\nd\ne\n")
        return cmd_save(str(f), op["base_sha"], actor, b"a\nb\nc\nd\nE\n")

    h_dir = tmp_path / "human"
    p_dir = tmp_path / "process"
    h_dir.mkdir()
    p_dir.mkdir()

    r_h = run("emacs", h_dir)
    r_p = run("my-formatter", p_dir)
    # Same status, same mode, same merged content (sha equal because bytes equal).
    assert r_h["status"] == r_p["status"] == "saved"
    assert r_h["mode"] == r_p["mode"] == "merged"
    assert r_h["sha"] == r_p["sha"]
