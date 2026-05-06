"""`cotype resolve FILE' -- accept the user's hand-edit of FILE.

The git-style conflict-resolution flow
======================================

After `cotype save' produced a `conflict' outcome:

  - FILE on disk contains diff3 markers (`<<<<<<<` / `=======` /
    `>>>>>>>') spanning the conflicting regions.
  - The sidecar's `state.json' records `pending_conflict' with the
    forensic dump path.
  - Further `cotype save' calls raise `ConflictPending'.

The user's job is to:

  1. Open FILE in their editor.
  2. See the markers, decide what the right resolution is, and edit
     the markers out -- producing a clean file with their preferred
     resolution.
  3. Save the buffer (in editors with `cotype-mode' enabled, this
     would normally route through `cotype save', which would be
     refused with `ConflictPending'; the editor companion handles
     this by writing the buffer to disk via a non-cotype path).
  4. Run `cotype resolve FILE'.

`cotype resolve' then:

  - Reads FILE off disk.
  - Refuses (with `UsageError') if any line still starts with
    `<<<<<<< ' OR `>>>>>>> ' -- the user hasn't finished editing.
  - Otherwise, hashes FILE's content, stores it as a new base,
    updates `last_known_sha', and clears `pending_conflict'.

The marker-detection heuristic
==============================

`_has_conflict_markers' returns True iff the content contains BOTH a
`<<<<<<< ` opener AND a `>>>>>>> ` closer line. Requiring BOTH (not
either alone) is what makes the heuristic robust on natural text:

  - A line starting with `<<<<<<< ` is essentially impossible in
    real prose: 7 `<' chars in a row, followed by a space, is not
    something humans type.
  - A line starting with `>>>>>>> ` (e.g., quoted-quoted-quoted in
    an email or an unusual prompt) is also almost impossible.
  - But a lone `=======' (no leading `<<<` or `>>>`) is a plausible
    Markdown Setext H1 underline, like:

        Title
        =====

    So we'd false-positive on it if we matched on `=======` alone.

Requiring opener AND closer both present is the conjunction that
nails down "this is a real diff3 marker block" without unwanted
false-positives. It does mean a user who deletes ONLY the opener
(but leaves a `=======' and `>>>>>>> ' below) gets through the check
-- but that file is malformed in a different way, the user clearly
intended *something*, and resolve takes their bytes as-is.

Why no `--actor' has any effect
================================

The `actor' arg is accepted for symmetry with `cotype save', and to
let editor plugins pass `--actor emacs' through unchanged for
consistency. But cotype does NOT record the resolver's identity --
the conflict is closed regardless of who ran resolve. Future
features may want to log "who resolved", in which case the field
becomes meaningful; today it's a no-op.

Spec refs: kb/spec/algorithms.md#resolve
Properties enforced: P4 (cleanup post-resolve), P12.
"""
from __future__ import annotations

from cotype.errors import InvalidUtf8, IoError, UnmanagedFile, UsageError
from cotype.hash import hash_bytes
from cotype.lock import sidecar_lock
from cotype.paths import resolve_target, sidecar_dir
from cotype.store import read_state, state_exists, store_base, write_state


def _has_conflict_markers(content: bytes) -> bool:
    """Detect leftover diff3 conflict markers.

    Returns True iff `content' contains BOTH a `<<<<<<< ` opener line
    AND a `>>>>>>> ` closer line. Requiring both rules out
    false-positives on Setext-style Markdown headings (which use
    `=======' as an H1 underline and would trigger a single-marker
    check).

    The check is line-prefix based, not regex: a line that "contains"
    `<<<<<<< ' midway through is deliberately ignored, because the
    only realistic source of those characters at column 0 is a real
    diff3 marker.
    """
    has_open = False
    has_close = False
    for line in content.splitlines():
        if line.startswith(b"<<<<<<< "):
            has_open = True
        if line.startswith(b">>>>>>> "):
            has_close = True
        if has_open and has_close:
            return True
    return False


def cmd_resolve(file_arg: str, actor: str = "unknown") -> dict:
    """Read FILE, validate no markers, clear `state.pending_conflict'.

    Returns the JSON envelope:
        {"status": "resolved", "file": "...", "sha": "sha256:..."}

    Raises:
        UnmanagedFile -- no sidecar.
        UsageError    -- (a) no pending conflict, OR (b) FILE still
                         contains diff3 markers.
        InvalidUtf8   -- FILE on disk is not valid UTF-8.
        IoError       -- can't read FILE.
    """
    file = resolve_target(file_arg)
    sidecar = sidecar_dir(file)
    if not state_exists(sidecar):
        raise UnmanagedFile(f"{file} is not managed by cotype")

    with sidecar_lock(sidecar):
        st = read_state(sidecar)
        if st.pending_conflict is None:
            # `resolve' on a clean sidecar is almost always user
            # error. We could no-op silently, but a clear `UsageError'
            # makes the situation visible.
            raise UsageError("no pending conflict to resolve")

        try:
            content = file.read_bytes()
        except OSError as e:
            raise IoError(f"reading {file}: {e}") from e
        try:
            content.decode("utf-8")
        except UnicodeDecodeError as e:
            raise InvalidUtf8(f"{file} is not valid UTF-8") from e
        if _has_conflict_markers(content):
            # The user pressed `cotype resolve' before finishing the
            # edit. Tell them clearly so they go back, finish the
            # edit, and try again.
            raise UsageError(
                f"{file} still contains conflict markers; "
                f"edit them out and re-run `cotype resolve`"
            )

        # The bytes on disk ARE the resolution. Hash, store as a new
        # base, and clear the pending state.
        sha = hash_bytes(content)
        store_base(sidecar, content, sha)
        st.last_known_sha = sha
        st.pending_conflict = None
        write_state(sidecar, st)

    # `actor' is informational only; we accept it for symmetry with
    # `cotype save' but never record it.
    _ = actor
    return {"status": "resolved", "file": str(file), "sha": sha}
