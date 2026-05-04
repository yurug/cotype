"""3-way merge via POSIX `diff3 -m`.

Spec refs: kb/spec/algorithms.md#merge3-internal, kb/external/diff3.md,
           kb/architecture/decisions/0002-diff3-for-merge.md
Properties enforced: P10 -- a missing or broken `diff3` is a tool error,
NOT a content conflict.

Argument order: PROPOSED is "MYFILE" (favoured side of conflict markers),
BASE is the common ancestor, CURRENT is "YOURFILE". Matches SPEC §8.
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
    merged: bytes


@dataclass(frozen=True)
class Conflict:
    merged_with_markers: bytes


MergeResult = Union[Clean, Conflict]


def merge3(
    base: bytes, current: bytes, proposed: bytes, sidecar: Path
) -> MergeResult:
    """Run `diff3 -m PROPOSED BASE CURRENT` and classify the outcome.

    Returns:
        Clean(merged)            -- diff3 exit 0; merged content in stdout.
        Conflict(merged_markers) -- diff3 exit 1; stdout has <<<<<<<======>>>>>>>.

    Raises:
        MergeToolError -- diff3 missing on PATH OR exit code >= 2.
    """
    tmp = tmp_dir(sidecar)
    try:
        tmp.mkdir(parents=True, exist_ok=True)
    except OSError as e:
        raise MergeToolError(f"could not prepare merge tmp dir {tmp}: {e}") from e

    paths: list[str] = []
    try:
        # Order matters: proposed, base, current -- the "MYFILE OLDFILE YOURFILE" trio.
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
                # fdopen took ownership; on failure remove the file we created.
                try:
                    Path(name).unlink(missing_ok=True)
                except OSError:
                    pass
                raise
            paths.append(name)

        try:
            r = subprocess.run(
                ["diff3", "-m", paths[0], paths[1], paths[2]],
                capture_output=True,
                check=False,
            )
        except FileNotFoundError as e:
            raise MergeToolError(
                "diff3 not found on PATH; install diffutils"
            ) from e
        except OSError as e:
            raise MergeToolError(f"could not invoke diff3: {e}") from e

        # P10: classify strictly by exit code.
        if r.returncode == 0:
            return Clean(merged=r.stdout)
        if r.returncode == 1:
            return Conflict(merged_with_markers=r.stdout)
        raise MergeToolError(
            f"diff3 exited {r.returncode}: "
            f"{r.stderr.decode('utf-8', errors='replace').strip()}"
        )
    finally:
        for p in paths:
            try:
                Path(p).unlink(missing_ok=True)
            except OSError:
                pass
