"""Sidecar persistence -- `state.json' read/write and base storage.

What this module manages
========================

Two things on disk:

  1. `state.json' -- a small, atomically-written record of the
     sidecar's current state. Schema (current FORMAT_VERSION = 1):

        {
          "format_version": 1,
          "target_path":    "../FILE",            # relative, informational
          "last_known_sha": "sha256:<64 hex>",    # H of latest base
          "pending_conflict": null | {
            "id":           "<32 hex>",
            "base_sha":     "sha256:...",
            "current_sha":  "sha256:...",
            "proposed_sha": "sha256:...",
            "path":         "<sidecar>/conflicts/<id>"
          }
        }

  2. `bases/<hex>' -- one file per captured base snapshot, addressed
     by the 64-char hex of its SHA-256. Idempotent on identical
     content (re-storing a base whose hash already exists is a no-op).

Why JSON for state? It's stdlib, human-inspectable for forensics, and
the schema is small enough that the validation code below is short.
The alternative (a custom binary format) would be faster but the
state.json IO path is single-digit microseconds of either, and JSON
wins big on debuggability.

The lock contract
=================

Every public function here ASSUMES the caller holds the sidecar
flock (per ADR-0003). store.py never acquires it -- attempting to
do so would deadlock against the caller. Calling sites are exactly
the implementations under `commands/'; if you add a new caller, take
the lock first.

State.from_json validates aggressively: any field that's missing,
the wrong type, or has an unknown `format_version' raises
`CorruptSidecar'. We do this instead of "fix it up best we can"
because a corrupt state.json is a sign of either external tampering
or a cotype bug, and quietly papering over either makes the next
debugging session much harder.

Format-version policy
=====================

Bumping `FORMAT_VERSION' is a sidecar-format break. The migration
strategy isn't built yet (the project is still on v1 of the format);
when v2 lands, expect either a `cotype migrate' command or a
documented "delete the sidecar and re-init" flow. For now,
`format_version != 1' is a hard refuse.

Spec refs: kb/spec/data-model.md, kb/spec/config-and-formats.md
"""
from __future__ import annotations

import json
from dataclasses import asdict, dataclass
from pathlib import Path
from typing import Optional

from cotype.atomic_write import atomic_replace
from cotype.errors import CorruptSidecar, IoError
from cotype.hash import hex_part
from cotype.paths import base_path

FORMAT_VERSION = 1


@dataclass
class PendingConflict:
    """One pending conflict's metadata.

    Created by `commands/save.py' when a 3-way merge fails; cleared
    by `commands/resolve.py' once the user has edited markers out and
    accepted the resulting file. While set, ordinary saves raise
    `ConflictPending' -- the user must resolve before more state can
    accumulate.

    Fields:
        id            -- 32 hex chars (uuid4 hex). Names a directory
                         under `<sidecar>/conflicts/'.
        base_sha      -- the snapshot the conflicting save was made
                         against.
        current_sha   -- what was on disk at the time of conflict.
        proposed_sha  -- what the conflicting save tried to write.
        path          -- absolute path to the conflict dir, for the
                         convenience of consumers of the JSON
                         envelope.
    """
    id: str
    base_sha: str
    current_sha: str
    proposed_sha: str
    path: str


@dataclass
class State:
    """In-memory shape of state.json.

    `format_version` is here so that future code reading an old
    state.json can decide whether to migrate, refuse, or reformat.
    Today the only supported value is 1.
    """
    target_path: str
    last_known_sha: str
    pending_conflict: Optional[PendingConflict] = None
    format_version: int = FORMAT_VERSION

    def to_json(self) -> str:
        """Serialize to the canonical JSON form (`indent=2', trailing newline).

        Stable on round-trip: parsing this output through `from_json'
        and re-serializing gives byte-identical bytes (modulo
        Python's JSON ordering, which `dataclasses.asdict' makes
        deterministic for our shape).
        """
        d = {
            "format_version": self.format_version,
            "target_path": self.target_path,
            "last_known_sha": self.last_known_sha,
            "pending_conflict": (
                asdict(self.pending_conflict) if self.pending_conflict else None
            ),
        }
        return json.dumps(d, indent=2) + "\n"

    @staticmethod
    def from_json(text: str) -> "State":
        """Parse + validate state.json text. Strict on missing/typed fields.

        Why strict: a state.json that's almost-right but missing a
        field is far more likely to be a bug or external tamper than
        a benign omission. We refuse it cleanly so the user sees a
        `CorruptSidecar' and can decide what to do, rather than
        carrying corrupt state forward into a save that might lose
        work.
        """
        try:
            d = json.loads(text)
        except json.JSONDecodeError as e:
            raise CorruptSidecar(f"state.json is not valid JSON: {e}") from e
        if not isinstance(d, dict):
            raise CorruptSidecar("state.json must be a JSON object")
        if d.get("format_version") != FORMAT_VERSION:
            raise CorruptSidecar(
                f"unsupported format_version {d.get('format_version')!r}"
            )
        for key in ("target_path", "last_known_sha"):
            if key not in d or not isinstance(d[key], str):
                raise CorruptSidecar(f"state.json missing/wrong-typed: {key}")
        pc_raw = d.get("pending_conflict")
        pc: Optional[PendingConflict] = None
        if pc_raw is not None:
            if not isinstance(pc_raw, dict):
                raise CorruptSidecar(
                    "pending_conflict must be a JSON object or null"
                )
            try:
                pc = PendingConflict(
                    id=pc_raw["id"],
                    base_sha=pc_raw["base_sha"],
                    current_sha=pc_raw["current_sha"],
                    proposed_sha=pc_raw["proposed_sha"],
                    path=pc_raw["path"],
                )
            except KeyError as e:
                raise CorruptSidecar(f"pending_conflict missing field {e}") from e
        return State(
            target_path=d["target_path"],
            last_known_sha=d["last_known_sha"],
            pending_conflict=pc,
        )


def state_path(sidecar: Path) -> Path:
    """Path to state.json inside the sidecar."""
    return sidecar / "state.json"


def ensure_layout(sidecar: Path) -> None:
    """Create the sidecar's directory layout if absent. Idempotent.

    Layout: `<sidecar>/' itself plus `bases/', `conflicts/', `tmp/'.
    Does NOT write state.json -- that's the caller's job after
    capturing the very first base. Reason: writing state.json before
    we have a `last_known_sha' would force us to invent a placeholder
    sentinel, and getting that wrong is exactly the kind of bug a
    strict from_json would catch with a confusing message.
    """
    try:
        sidecar.mkdir(parents=True, exist_ok=True)
        (sidecar / "bases").mkdir(exist_ok=True)
        (sidecar / "conflicts").mkdir(exist_ok=True)
        (sidecar / "tmp").mkdir(exist_ok=True)
    except OSError as e:
        raise IoError(
            f"could not create sidecar layout under {sidecar}: {e}"
        ) from e


def state_exists(sidecar: Path) -> bool:
    """True iff the sidecar appears initialised (has a state.json).

    Useful from commands that decide between "this file is managed,
    proceed" and "no sidecar yet, raise UnmanagedFile".
    """
    return state_path(sidecar).exists()


def read_state(sidecar: Path) -> State:
    """Read and validate state.json. Raises `CorruptSidecar' on malformation."""
    p = state_path(sidecar)
    try:
        text = p.read_text(encoding="utf-8")
    except FileNotFoundError as e:
        raise CorruptSidecar(f"state.json missing under {sidecar}") from e
    except OSError as e:
        raise IoError(f"reading state.json: {e}") from e
    return State.from_json(text)


def write_state(sidecar: Path, st: State) -> None:
    """Write state.json atomically. A torn write leaves the previous version intact.

    The atomicity comes for free from `atomic_replace' -- a crash
    between the two cotype lines below cannot leave half a state.json
    on disk; either the OLD file is intact (the rename hasn't
    happened yet) or the NEW file is intact (the rename has).
    """
    atomic_replace(state_path(sidecar), st.to_json().encode("utf-8"), sidecar)


def store_base(sidecar: Path, content: bytes, sha: str) -> Path:
    """Persist `content' at `bases/<hex>'. Idempotent on identical content.

    `sha' MUST equal `H(content)'; we trust the caller to have
    computed the hash already (almost every caller did, when they
    decided whether they were dealing with a known or unknown base).

    Returns the path to the stored base -- mostly for the
    convenience of `cmd_open', which embeds it into the JSON envelope
    so callers can read content from there instead of re-reading
    FILE (avoiding the documented "forbidden protocol" race).

    Idempotence: if `bases/<hex>' already exists, we DO NOT
    re-write it. Re-writing would be:
      - useless (same content, by hash equivalence),
      - wasteful (an atomic write is non-trivial work),
      - subtly racy in the sense that another process holding an
        open fd into the old file across our rename would get a
        different inode pointing at identical bytes.
    """
    hex64 = hex_part(sha)
    target = base_path(sidecar, hex64)
    if target.exists():
        return target
    atomic_replace(target, content, sidecar)
    return target
