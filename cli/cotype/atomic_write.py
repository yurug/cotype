"""Atomic file replacement -- the canonical save ritual.

Every byte of content cotype publishes to disk goes through this
function. There is no other "write a file" path in the package.

The ritual
==========

    1. Create a fresh temp file inside `<sidecar>/tmp/'.
    2. Write the new bytes; flush; fsync the temp's data.
    3. Copy mode bits (and best-effort uid/gid) from the existing
       target onto the temp.
    4. `os.replace(tmp, target)' -- the atomic rename.
    5. fsync the target's parent directory so the rename itself
       survives a crash.

Each step is doing real work; skipping any of them either breaks
atomicity or breaks durability:

    Step 1 (temp on same fs)   -- `os.replace' across filesystems
                                  fails with EXDEV. The sidecar's
                                  `tmp/` subdir lives next to FILE,
                                  so they're guaranteed same-fs.
    Step 2 (fsync data)        -- without this, a crash between
                                  rename and the dirty page write-
                                  back can leave FILE pointing at
                                  zeroed-out blocks. Classic ext4
                                  gotcha that nuked many an editor
                                  in the early 2010s.
    Step 3 (copy mode/owner)   -- otherwise our temp's mode (0600
                                  from `mkstemp', owned by us) would
                                  silently replace the original's
                                  mode. P13 ("mode preserved")
                                  matters because cotype is allowed
                                  to manage files like `~/.ssh/config'.
    Step 4 (atomic rename)     -- on POSIX `rename' is atomic and
                                  observable: a concurrent reader of
                                  FILE sees either the OLD bytes
                                  in their entirety or the NEW bytes
                                  in their entirety, never a mix.
                                  This is P2 (atomic visibility).
    Step 5 (fsync the dir)     -- the rename creates a directory-
                                  entry change that's only durable
                                  once the parent dir is fsync'd.
                                  Without this, a power loss right
                                  after `os.replace' could leave the
                                  directory pointing at the old
                                  inode after recovery, even though
                                  the new data was already on disk.

The mode-bit and chown steps are intentionally tolerant: a `chown'
failure on a non-root cotype process is normal (we lack CAP_CHOWN),
and we don't want save to fail just because we can't preserve the
original `uid:gid' verbatim. We do log neither result -- it's
best-effort and silent. If someone runs `cotype save' on a file they
don't own, the resulting file is owned by the cotype process, which
is exactly what running an editor as themselves would also do.

Caller contract
===============

The caller MUST already hold `sidecar_lock'. Lower layers
deliberately do not acquire the lock -- that would deadlock with the
caller, who already holds it.

If any step before `os.replace' raises, FILE is left untouched and
the temp is cleaned up. If `os.replace' itself raises (very rare;
implies a kernel/filesystem failure), the temp may leak; we attempt
cleanup but don't try too hard.

Spec refs: kb/spec/algorithms.md#atomic-replace, kb/external/posix-fs.md
Properties enforced: P2 (atomic visibility), P12 (atomic replace),
P13 (mode preservation).
"""
from __future__ import annotations

import os
import shutil
import tempfile
from pathlib import Path

from cotype.errors import IoError
from cotype.paths import tmp_dir


def atomic_replace(target: Path, content: bytes, sidecar: Path) -> None:
    """Replace `target` with `content` atomically.

    See module docstring for the full ritual and the rationale behind
    each step. The function is intentionally medium-length and free of
    helpers -- the ordering and the error-handling shape are the
    interesting bits, and inlining keeps them visible.

    Args:
        target  -- the file whose contents are being replaced.
        content -- exactly the bytes that will land on disk.
        sidecar -- the sidecar dir, used to locate `tmp/`.
    """
    tmp = tmp_dir(sidecar)
    try:
        tmp.mkdir(parents=True, exist_ok=True)
    except OSError as e:
        raise IoError(f"could not prepare tmp dir {tmp}: {e}") from e

    # `mkstemp' is the right primitive here: O_EXCL create, secure
    # permissions (mode 0600), unguessable name. Predictable temp
    # names would open a race for an attacker that controls the tmp
    # dir; we own this dir but defence in depth is cheap.
    try:
        fd, tmp_name = tempfile.mkstemp(prefix="atomic-", dir=str(tmp))
    except OSError as e:
        raise IoError(f"could not create temp file in {tmp}: {e}") from e

    tmp_path = Path(tmp_name)
    try:
        # Write + flush + fsync the data before any rename. The
        # `with' block also closes the fd which flushes the C stdio
        # buffer; the explicit `f.flush()' is a no-op for the byte
        # stream we get from `os.fdopen` but kept as a documentation
        # marker of "user-space buffers cleared before fsync".
        with os.fdopen(fd, "wb") as f:
            f.write(content)
            f.flush()
            os.fsync(f.fileno())

        # Preserve permissions only when the target already exists --
        # the freshly-init case has no target yet to copy from.
        if target.exists():
            try:
                shutil.copymode(target, tmp_path)
            except OSError:
                # Mode preservation is best-effort. If we can't read
                # the source's mode, the file lands with `mkstemp''s
                # 0600 default -- which is sometimes what users want
                # (private by default) and sometimes annoying. We've
                # decided not to fail save on this.
                pass
            try:
                st = target.stat()
                os.chown(tmp_path, st.st_uid, st.st_gid)
            except (PermissionError, OSError):
                # `chown' to a different uid requires CAP_CHOWN; on
                # an unprivileged save (the common case) we lose the
                # original ownership. Acceptable tradeoff: failing
                # the save here would mean a non-root cotype could
                # never overwrite a file it doesn't own.
                pass

        # The atomic step. From this point on, readers see either the
        # old file or the new file -- never half-and-half. (Provided
        # we held the sidecar lock, no other cotype process is in
        # flight; provided no rogue writer ignores the protocol.)
        os.replace(tmp_path, target)

        # Durability of the rename itself. On Linux/macOS the
        # documented incantation is to open the parent dir for
        # reading and fsync it. EFAULT/ENOTDIR/etc. are best-effort
        # ignored: we still completed the write, the user just gets
        # weaker durability guarantees in the very rare crash window.
        parent = target.parent
        try:
            dir_fd = os.open(parent, os.O_RDONLY)
        except OSError:
            return
        try:
            os.fsync(dir_fd)
        finally:
            os.close(dir_fd)
    except OSError as e:
        # If we never reached `os.replace', the temp file is still on
        # disk and useless to anyone. Tidy it up so we don't leak
        # stragglers in `<sidecar>/tmp/' over time.
        try:
            tmp_path.unlink(missing_ok=True)
        except OSError:
            pass
        raise IoError(f"atomic replace of {target} failed: {e}") from e
