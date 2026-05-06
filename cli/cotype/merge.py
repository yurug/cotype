"""3-way merge via POSIX `diff3 -m`.

Why a subprocess wrapper, why diff3, and what to watch for
==========================================================

cotype's "merge" step is delegated to the venerable POSIX `diff3 -m`
(from `diffutils', present on every Linux/macOS by default). That's
deliberate -- ADR-0002 spells it out:

  - Reusing diff3 means we don't write our own merge engine. Merge
    correctness is hard; reaching for a battle-tested 40-year-old
    utility is the right tradeoff for KISS.
  - A subprocess hop costs ~5-20 ms per save. That's real, but only
    on a stale-base + non-noop save (the path that needs a merge);
    direct writes and noops never reach this module.
  - The output is byte-for-byte the same diff3 markers users already
    know from git. No new vocabulary to learn.

The argument-order trap
=======================

`diff3 -m MYFILE OLDFILE YOURFILE` -- and the order matters because
MYFILE is the "favoured" side in the conflict markers (`<<<<<<<
MYFILE / ||||||| OLDFILE / ======= / >>>>>>> YOURFILE`).

For cotype:
    MYFILE   = proposed   (the actor's submission)
    OLDFILE  = base       (the snapshot the actor started from)
    YOURFILE = current    (what's on disk now)

Getting this wrong gives correct-looking but wrong-sided merges, and
the bug is invisible in clean-merge cases (where output is identical
regardless of order). It only manifests on conflict, which is the
exact failure mode we want to never debug. So: re-test if you ever
swap the args.

Exit-code classification (P10)
==============================

A diff3 invocation has three possible outcomes, classified strictly
by exit code:

    0  -> Clean(stdout)                    -- merged content
    1  -> Conflict(stdout)                  -- stdout has diff3 markers
    >=2 -> raise MergeToolError              -- diff3 itself broke

The third case (P10: "tool error is not content conflict") is
load-bearing. If diff3 is missing because `PATH' was clobbered, or
exits 2 because it got a malformed argument, we MUST NOT classify
that as a conflict -- doing so would record forensics that don't
match reality and leave the user with a "conflict" they can't
reproduce. The whole `try/except FileNotFoundError' below is in
service of this property.

Adjacent-edit conflicts (a real limitation)
===========================================

`diff3' is line-based and groups *contiguous* changed lines into one
region. Two edits on neighbouring lines fall in the same region and
report as a conflict EVEN IF the bytes don't literally overlap:

    base:     x\\ny\\nz\\n
    current:  x\\ny1\\nz\\n      # edits line 2
    proposed: x\\ny\\nz1\\n      # edits line 3
    -> CONFLICT

Inserting one unchanged line between the two edits separates the
regions. cotype accepts this conservatism without trying to be
smarter; the SPEC's "Clean is SHOULD (not MUST) for non-overlapping
edits" wording is exactly to leave room for it. The
`examples/headless-agents.sh' / `chorale' recipes work around it at
the harness level by splicing structurally per-section.

Spec refs: kb/spec/algorithms.md#merge3-internal,
           kb/external/diff3.md,
           kb/architecture/decisions/0002-diff3-for-merge.md
Properties enforced: P10
"""
from __future__ import annotations

import os
import subprocess
import tempfile
from dataclasses import dataclass
from pathlib import Path
from typing import Union

from cotype.errors import MergeToolError
from cotype.paths import tmp_dir


@dataclass(frozen=True)
class Clean:
    """diff3 produced a clean merge. `merged' is what to write to FILE."""
    merged: bytes


@dataclass(frozen=True)
class Conflict:
    """diff3 produced output containing `<<<<<<< / ======= / >>>>>>>` markers.

    `merged_with_markers' is exactly what we'll write to FILE so the
    user sees the conflict inline in their editor. cotype's
    `commands/save.py' does the actual write; this module just
    classifies and returns the bytes.
    """
    merged_with_markers: bytes


MergeResult = Union[Clean, Conflict]


def merge3(
    base: bytes, current: bytes, proposed: bytes, sidecar: Path
) -> MergeResult:
    """Run `diff3 -m PROPOSED BASE CURRENT' and classify the outcome.

    Args:
        base, current, proposed -- the three sides as raw bytes.
        sidecar -- used to locate `tmp/' for the diff3 inputs (must be
                   on the same filesystem as the merge inputs to avoid
                   any cross-fs surprises).

    Returns:
        Clean(merged)            -- diff3 exit 0; merged content in stdout.
        Conflict(merged_markers) -- diff3 exit 1; stdout has markers.

    Raises:
        MergeToolError -- diff3 missing on PATH OR exit code >= 2.

    Subtleties:
        - We use list-form `subprocess.run' (never `shell=True') so
          arguments aren't subject to shell metachar interpretation.
        - We delete temp files in the `finally' block so a `diff3'
          crash doesn't leak `merge-*' files in `<sidecar>/tmp/'.
        - `diff3' may emit "no newline at end of file" warnings on
          stderr; those are informational and we deliberately don't
          inspect stderr to classify -- the exit code alone decides.
    """
    tmp = tmp_dir(sidecar)
    try:
        tmp.mkdir(parents=True, exist_ok=True)
    except OSError as e:
        raise MergeToolError(
            f"could not prepare merge tmp dir {tmp}: {e}"
        ) from e

    paths: list[str] = []
    try:
        # Order matters: proposed, base, current -- the
        # "MYFILE OLDFILE YOURFILE" trio. The named labels are also
        # what shows up in the temp filenames, so when a diff3
        # conflict ships markers like `<<<<<<< merge-proposed-XXXXX'
        # the user can see which side is which. Keeping the labels in
        # the file names is helpful for debugging stuck conflicts.
        for label, content in (
            ("proposed", proposed),
            ("base", base),
            ("current", current),
        ):
            fd, name = tempfile.mkstemp(prefix=f"merge-{label}-", dir=str(tmp))
            try:
                with os.fdopen(fd, "wb") as f:
                    f.write(content)
            except OSError:
                # `fdopen' took ownership of `fd', so the `with' close
                # would normally suffice -- but if `f.write' fails we
                # still want to remove the temp file we created.
                try:
                    Path(name).unlink(missing_ok=True)
                except OSError:
                    pass
                raise
            paths.append(name)

        # The actual merge call. List form, no shell. Capture stdout
        # for the merged bytes (clean OR with markers); capture
        # stderr for the diagnostic text we may include in a
        # MergeToolError message.
        try:
            r = subprocess.run(
                ["diff3", "-m", paths[0], paths[1], paths[2]],
                capture_output=True,
                check=False,
            )
        except FileNotFoundError as e:
            # `diff3' is missing on PATH. P10: this is a TOOL error,
            # not a content conflict. Reporting "conflict" here would
            # write forensics we can't reproduce.
            raise MergeToolError(
                "diff3 not found on PATH; install diffutils"
            ) from e
        except OSError as e:
            # Any other invocation-level failure (EACCES on the
            # binary, fork fail, etc.). Same P10 reasoning.
            raise MergeToolError(f"could not invoke diff3: {e}") from e

        # Classification is on EXIT CODE, not on whether stdout
        # contains markers. Exit code is the contract.
        if r.returncode == 0:
            return Clean(merged=r.stdout)
        if r.returncode == 1:
            return Conflict(merged_with_markers=r.stdout)
        raise MergeToolError(
            f"diff3 exited {r.returncode}: "
            f"{r.stderr.decode('utf-8', errors='replace').strip()}"
        )
    finally:
        # Clean up regardless of how we got here. The temp files are
        # in `<sidecar>/tmp/' and harmless if they leak, but a long-
        # running cotype install would accumulate cruft over time.
        for p in paths:
            try:
                Path(p).unlink(missing_ok=True)
            except OSError:
                pass
