"""`stile save FILE --base-sha HASH < proposed`.

Outcomes: direct | merged | noop | conflict (and any error).

Spec refs: kb/spec/algorithms.md#save
Properties enforced: P1 (no silent stale overwrite), P4 (conflicts explicit),
P5, P6, P7 (pending blocks save), P8 (unknown base), P10 (tool error not
content conflict), P12, P13, P14 (noop short-circuit).
"""
from __future__ import annotations

import datetime as dt
import json
import uuid

from stile.atomic_write import atomic_replace
from stile.errors import (
    ConflictPending,
    InvalidUtf8,
    IoError,
    UnknownBase,
    UnmanagedFile,
)
from stile.hash import hash_bytes, hex_part
from stile.lock import sidecar_lock
from stile.merge import Clean, Conflict, merge3
from stile.paths import (
    base_path,
    conflict_dir,
    resolve_target,
    sidecar_dir,
)
from stile.store import (
    PendingConflict,
    read_state,
    state_exists,
    store_base,
    write_state,
)


def cmd_save(file_arg: str, base_sha: str, actor: str, proposed: bytes) -> dict:
    """Submit `proposed` against `base_sha` for `file_arg`.

    Branch order is load-bearing (kb/spec/algorithms.md#save):
        1. Reject pending conflict.
        2. Reject unknown base (after syntactic validation).
        3. Validate UTF-8 of current and proposed.
        4. Noop short-circuit (P14): proposed == current.
        5. Direct: caller's base == current.
        6. Otherwise: 3-way merge -> Clean (merged) or Conflict (conflict).
    """
    file = resolve_target(file_arg)
    sidecar = sidecar_dir(file)
    if not state_exists(sidecar):
        raise UnmanagedFile(
            f"{file} is not managed by stile (run `stile init` or `stile open` first)"
        )
    # Syntactic validation up front; an invalid HASH cannot name a real base.
    base_hex = hex_part(base_sha)

    with sidecar_lock(sidecar):
        st = read_state(sidecar)
        if st.pending_conflict is not None:
            raise ConflictPending(
                f"resolve conflict {st.pending_conflict.id} first "
                f"(see {st.pending_conflict.path})"
            )

        bases_file = base_path(sidecar, base_hex)
        if not bases_file.exists():
            raise UnknownBase(f"base snapshot {base_sha} is not present")

        try:
            base = bases_file.read_bytes()
        except OSError as e:
            raise IoError(f"reading base {bases_file}: {e}") from e
        try:
            current = file.read_bytes()
        except OSError as e:
            raise IoError(f"reading {file}: {e}") from e
        for label, b in (("current", current), ("proposed", proposed)):
            try:
                b.decode("utf-8")
            except UnicodeDecodeError as e:
                raise InvalidUtf8(f"{label} content is not valid UTF-8") from e

        prop_sha = hash_bytes(proposed)
        curr_sha = hash_bytes(current)

        # P14: short-circuit before any merge attempt.
        if prop_sha == curr_sha:
            store_base(sidecar, current, curr_sha)
            st.last_known_sha = curr_sha
            write_state(sidecar, st)
            return {"status": "saved", "mode": "noop", "sha": curr_sha}

        # Direct: base matches what's on disk.
        if curr_sha == base_sha:
            atomic_replace(file, proposed, sidecar)
            store_base(sidecar, proposed, prop_sha)
            st.last_known_sha = prop_sha
            write_state(sidecar, st)
            return {"status": "saved", "mode": "direct", "sha": prop_sha}

        # Stale base AND content differs: 3-way merge.
        result = merge3(base, current, proposed, sidecar)
        if isinstance(result, Clean):
            merged_sha = hash_bytes(result.merged)
            atomic_replace(file, result.merged, sidecar)
            store_base(sidecar, result.merged, merged_sha)
            st.last_known_sha = merged_sha
            write_state(sidecar, st)
            return {"status": "saved", "mode": "merged", "sha": merged_sha}

        # Conflict: forensics dump + state update; FILE untouched.
        assert isinstance(result, Conflict)
        cid = uuid.uuid4().hex
        cdir = conflict_dir(sidecar, cid)
        try:
            cdir.mkdir(parents=True, exist_ok=False)
            (cdir / "base").write_bytes(base)
            (cdir / "current").write_bytes(current)
            (cdir / "proposed").write_bytes(proposed)
            (cdir / "merged").write_bytes(result.merged_with_markers)
            meta = {
                "id": cid,
                "actor": actor,
                "base_sha": base_sha,
                "current_sha": curr_sha,
                "proposed_sha": prop_sha,
                "created_at": dt.datetime.now(dt.timezone.utc).strftime(
                    "%Y-%m-%dT%H:%M:%SZ"
                ),
            }
            (cdir / "meta.json").write_text(
                json.dumps(meta, indent=2) + "\n", encoding="utf-8"
            )
        except OSError as e:
            raise IoError(f"writing conflict dir {cdir}: {e}") from e

        st.pending_conflict = PendingConflict(
            id=cid,
            base_sha=base_sha,
            current_sha=curr_sha,
            proposed_sha=prop_sha,
            path=str(cdir),
        )
        write_state(sidecar, st)
        return {
            "status": "conflict",
            "conflict_id": cid,
            "conflict_path": str(cdir),
            "base_sha": base_sha,
            "current_sha": curr_sha,
            "proposed_sha": prop_sha,
        }
