"""`cotype save FILE --base-sha HASH < proposed' -- the heart of cotype.

What this module does
=====================

Take `proposed' bytes (from stdin) and try to publish them as the new
contents of FILE, against the caller's claimed `base_sha'. The
outcome is one of:

    direct    -- caller's base matches current; bytes written
                 atomically.
    merged    -- caller's base is stale, but a 3-way merge produced a
                 clean result.
    noop      -- proposed equals current; nothing to do.
    conflict  -- 3-way merge produced overlapping conflicts; FILE is
                 rewritten with diff3 markers, a forensic dump is
                 stored under `<sidecar>/conflicts/<id>/', and a
                 pending-conflict state is recorded. Subsequent saves
                 raise ConflictPending until the user resolves.

Branch order is load-bearing
============================

The decision tree below MUST run in this order. Reordering changes
the semantics in ways tests catch:

    1. Pending conflict?      -> raise ConflictPending (P7).
    2. Unknown base?          -> raise UnknownBase    (P8).
    3. Bytes UTF-8 OK?        -> raise InvalidUtf8.
    4. proposed == current?   -> "noop" save           (P14).
    5. base == current?       -> "direct" write        (P1 happy path).
    6. otherwise              -> 3-way merge:
                                   Clean   -> "merged".
                                   Conflict -> "conflict" + forensics.
                                   ToolError -> raise (P10).

Key reasoning behind the order:

  - Step 1 first. If a conflict is pending, no save can succeed, and
    we don't want to run a merge or do any I/O before bailing out.
  - Step 2 before any byte read. An invalid base never names a real
    snapshot, regardless of file content; reporting "unknown base" up
    front saves a pointless read.
  - Step 4 (noop) BEFORE step 5 (direct). The reason is subtle:
    consider the case where base is stale but proposed already
    equals current. Without the noop short-circuit, we'd do a 3-way
    merge that has nothing to do (proposed == current, which is one
    side of the merge being identical to another). The merge would
    succeed cleanly but it would be more work than necessary, and on
    rare diff3 quirks could yield surprises. P14 makes idempotence
    explicit: "submitted exactly what's already on disk -> noop".

The conflict path: inline diff3 markers
=======================================

Cotype's conflict UX is the git-merge model: when a 3-way merge
fails, FILE is rewritten with `<<<<<<< / ======= / >>>>>>>' markers
spanning the conflicting regions, AND the sidecar records pending
state. The user opens FILE in their editor, sees the markers, edits
them out, and runs `cotype resolve' to clear the pending state.

Why inline (and not "leave FILE alone, dump to sidecar"): when the
file was rewritten with markers, the user sees the conflict in the
*place where they were already working*. The "navigate to the hidden
sidecar dir, find merged, edit there" alternative was tried in 0.1
and proved worse in practice -- users got lost in the sidecar layout
and the dance felt punitive. The inline-markers approach matches
what every git user already knows.

The cost of inline markers: invariant I4 in the PRD ("FILE unchanged
on conflict") is loosened to "FILE gets markers on conflict; further
saves are blocked until resolved." That tradeoff is documented in
the CHANGELOG for 0.2.0.

The forensic dump (under `<sidecar>/conflicts/<id>/`) is preserved so
a future analysis tool, or a frustrated user, can see exactly which
bytes the three sides had at conflict time. We never garbage-collect
this dir; it's small and the disk-usage cost is negligible vs. the
diagnostic value.

Spec refs: kb/spec/algorithms.md#save
Properties enforced: P1 (no silent stale overwrite), P4 (conflicts
explicit), P5, P6, P7 (pending blocks save), P8 (unknown base),
P10 (tool error not content conflict), P12, P13, P14 (noop
short-circuit).
"""
from __future__ import annotations

import datetime as dt
import json
import uuid

from cotype.atomic_write import atomic_replace
from cotype.errors import (
    ConflictPending,
    InvalidUtf8,
    IoError,
    UnknownBase,
    UnmanagedFile,
)
from cotype.hash import hash_bytes, hex_part
from cotype.lock import sidecar_lock
from cotype.merge import Clean, Conflict, merge3
from cotype.paths import (
    base_path,
    conflict_dir,
    resolve_target,
    sidecar_dir,
)
from cotype.store import (
    PendingConflict,
    read_state,
    state_exists,
    store_base,
    write_state,
)


def cmd_save(file_arg: str, base_sha: str, actor: str, proposed: bytes) -> dict:
    """Submit `proposed' against `base_sha' for `file_arg'.

    See module docstring for the branch order and rationale. The
    function is intentionally one long body rather than split into
    helpers -- the order of operations IS the algorithm, and inlining
    keeps it visible at a glance.

    Args:
        file_arg  -- the user's path argument; resolved via
                     `resolve_target'.
        base_sha  -- "sha256:<hex>" the caller claims they edited
                     against. Validated via `hex_part'.
        actor     -- free-form label, recorded in conflict meta.json.
                     Never affects semantics.
        proposed  -- the bytes the caller wants on disk.

    Returns:
        One of the four `mode' envelopes documented in
        kb/spec/api-contracts.md#cotype-save.

    Raises:
        UnmanagedFile     -- no sidecar.
        UnknownBase       -- bad base_sha.
        ConflictPending   -- a previous conflict isn't resolved yet.
        InvalidUtf8       -- current or proposed bytes don't decode.
        IoError           -- any other OS-level failure.
        MergeToolError    -- diff3 missing or broken (raised by merge3).
    """
    file = resolve_target(file_arg)
    sidecar = sidecar_dir(file)
    if not state_exists(sidecar):
        raise UnmanagedFile(
            f"{file} is not managed by cotype "
            f"(run `cotype init` or `cotype open` first)"
        )
    # Syntactic validation of base_sha BEFORE we take the lock or do
    # any I/O. An invalid HASH can never name a real base, and we
    # want the caller to find that out quickly.
    base_hex = hex_part(base_sha)

    with sidecar_lock(sidecar):
        st = read_state(sidecar)
        # P7: refuse if a conflict is already pending. The user must
        # resolve before more state can pile up.
        if st.pending_conflict is not None:
            raise ConflictPending(
                f"resolve conflict {st.pending_conflict.id} first "
                f"(see {st.pending_conflict.path})"
            )

        bases_file = base_path(sidecar, base_hex)
        if not bases_file.exists():
            # P8: an unknown base means the caller is working from a
            # state cotype no longer remembers. We can't merge
            # against a base we've never stored.
            raise UnknownBase(f"base snapshot {base_sha} is not present")

        try:
            base = bases_file.read_bytes()
        except OSError as e:
            raise IoError(f"reading base {bases_file}: {e}") from e
        try:
            current = file.read_bytes()
        except OSError as e:
            raise IoError(f"reading {file}: {e}") from e
        # Validate UTF-8 of both sides we'll feed diff3. Doing this
        # under the lock guarantees no concurrent write changes the
        # bytes between now and when diff3 runs (if it does).
        for label, b in (("current", current), ("proposed", proposed)):
            try:
                b.decode("utf-8")
            except UnicodeDecodeError as e:
                raise InvalidUtf8(
                    f"{label} content is not valid UTF-8"
                ) from e

        prop_sha = hash_bytes(proposed)
        curr_sha = hash_bytes(current)

        # P14: noop short-circuit. The caller submitted exactly what's
        # already on disk; no merge needed, no write needed. Refresh
        # `last_known_sha' to reflect the agreed-upon current bytes.
        if prop_sha == curr_sha:
            store_base(sidecar, current, curr_sha)
            st.last_known_sha = curr_sha
            write_state(sidecar, st)
            return {"status": "saved", "mode": "noop", "sha": curr_sha}

        # Direct save: caller's base IS what's on disk. Atomically
        # replace FILE with proposed bytes. P1 (no silent stale
        # overwrite) is preserved -- the equality check above is
        # what makes it safe to overwrite.
        if curr_sha == base_sha:
            atomic_replace(file, proposed, sidecar)
            store_base(sidecar, proposed, prop_sha)
            st.last_known_sha = prop_sha
            write_state(sidecar, st)
            return {"status": "saved", "mode": "direct", "sha": prop_sha}

        # Stale base AND content differs: hand off to 3-way merge.
        # Three outcomes from `merge3' (see merge.py for details):
        #   Clean(merged)            -- diff3 succeeded.
        #   Conflict(merged_markers) -- diff3 returned with markers.
        #   raise MergeToolError     -- diff3 broken or missing (P10).
        result = merge3(base, current, proposed, sidecar)
        if isinstance(result, Clean):
            merged_sha = hash_bytes(result.merged)
            atomic_replace(file, result.merged, sidecar)
            store_base(sidecar, result.merged, merged_sha)
            st.last_known_sha = merged_sha
            write_state(sidecar, st)
            return {
                "status": "saved",
                "mode": "merged",
                "sha": merged_sha,
            }

        # Conflict path. Three jobs to do, in order:
        #   1. Persist a forensic dump (the three sides + meta.json).
        #   2. Atomically rewrite FILE with the diff3 marker output.
        #   3. Record `pending_conflict' in state.json.
        # All three succeed or all three fail (we hold the lock; we
        # use atomic_replace for the FILE write; the conflict dir
        # write is the one weak link, and on its failure we raise
        # without recording state, leaving the sidecar consistent).
        assert isinstance(result, Conflict)
        cid = uuid.uuid4().hex
        cdir = conflict_dir(sidecar, cid)
        try:
            # `mkdir(exist_ok=False)` because uuid4 collisions are
            # astronomical; if we somehow hit one, raising is the
            # right behaviour rather than silently sharing a dir
            # with another conflict.
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

        # Inline markers: write the merged-with-markers content into
        # FILE. The user opens FILE in their editor and sees the
        # conflict in place; `cotype resolve' (after the user has
        # edited markers out) clears the pending state.
        markers_sha = hash_bytes(result.merged_with_markers)
        atomic_replace(file, result.merged_with_markers, sidecar)
        store_base(sidecar, result.merged_with_markers, markers_sha)
        st.pending_conflict = PendingConflict(
            id=cid,
            base_sha=base_sha,
            current_sha=curr_sha,
            proposed_sha=prop_sha,
            path=str(cdir),
        )
        # `last_known_sha' is now the markers content -- subsequent
        # `cotype open' on this file returns that hash, which is
        # consistent with what's actually on disk.
        st.last_known_sha = markers_sha
        write_state(sidecar, st)
        return {
            "status": "conflict",
            "conflict_id": cid,
            "conflict_path": str(cdir),
            "base_sha": base_sha,
            "current_sha": curr_sha,
            "proposed_sha": prop_sha,
            "markers_sha": markers_sha,
        }
