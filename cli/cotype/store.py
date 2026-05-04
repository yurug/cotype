"""Sidecar persistence: state.json read/write, base storage.

Spec refs: kb/spec/data-model.md, kb/spec/config-and-formats.md

The lock contract: every public function here ASSUMES the caller holds the
sidecar flock (per ADR-0003). store.py never acquires it -- attempting to
do so would deadlock.
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
    id: str
    base_sha: str
    current_sha: str
    proposed_sha: str
    path: str


@dataclass
class State:
    target_path: str
    last_known_sha: str
    pending_conflict: Optional[PendingConflict] = None
    format_version: int = FORMAT_VERSION

    def to_json(self) -> str:
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
                raise CorruptSidecar("pending_conflict must be a JSON object or null")
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
    return sidecar / "state.json"


def ensure_layout(sidecar: Path) -> None:
    """Create the sidecar dirs (sidecar/, bases/, conflicts/, tmp/) if absent.

    Idempotent. Does not write state.json -- that's the caller's job.
    """
    try:
        sidecar.mkdir(parents=True, exist_ok=True)
        (sidecar / "bases").mkdir(exist_ok=True)
        (sidecar / "conflicts").mkdir(exist_ok=True)
        (sidecar / "tmp").mkdir(exist_ok=True)
    except OSError as e:
        raise IoError(f"could not create sidecar layout under {sidecar}: {e}") from e


def state_exists(sidecar: Path) -> bool:
    """True iff sidecar appears initialised (has a state.json)."""
    return state_path(sidecar).exists()


def read_state(sidecar: Path) -> State:
    """Read and validate state.json. Raises CorruptSidecar on malformation."""
    p = state_path(sidecar)
    try:
        text = p.read_text(encoding="utf-8")
    except FileNotFoundError as e:
        raise CorruptSidecar(f"state.json missing under {sidecar}") from e
    except OSError as e:
        raise IoError(f"reading state.json: {e}") from e
    return State.from_json(text)


def write_state(sidecar: Path, st: State) -> None:
    """Write state.json atomically. A torn write leaves the previous version intact."""
    atomic_replace(state_path(sidecar), st.to_json().encode("utf-8"), sidecar)


def store_base(sidecar: Path, content: bytes, sha: str) -> Path:
    """Persist `content` at bases/<hex>. Idempotent on identical content.

    `sha` MUST be H(content); we trust the caller to have computed it once.
    Returns the path to the stored base.
    """
    hex64 = hex_part(sha)
    target = base_path(sidecar, hex64)
    if target.exists():
        return target
    atomic_replace(target, content, sidecar)
    return target
