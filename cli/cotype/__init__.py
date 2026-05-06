"""cotype -- universal safe-save for concurrent text files.

What this package is
====================

A tiny CLI that prevents lost updates when many actors save changes
to the same regular text file at the same time -- you in your editor,
an AI agent, a build hook, a formatter, a sync script, anything.

The mental model is intentionally small:

    open  -- capture the current bytes of FILE as a base snapshot.
    save  -- submit candidate bytes against a base; cotype writes
             them atomically, 3-way-merges, decides "no change", or
             surfaces a conflict.
    fail  -- on conflict, FILE is rewritten with diff3 markers and
             a pending state is recorded; further saves are blocked
             until `cotype resolve' clears it.

If you've ever overwritten work because two writers raced on the
same file, or had to wire up `flock` + `mv` + diff yourself, this is
that pattern packaged into one tool that does its job and stays out
of the way.

Module map (read in this order if you want the whole story)
===========================================================

  errors.py       Exception hierarchy + the JSON `error' name and
                  exit code each subclass guarantees. Stable wire
                  contract; renaming any of these is breaking.

  hash.py         SHA-256 over raw bytes. The single most important
                  invariant in the system: H(b) is byte-exact, no
                  normalisation. Without this, two actors disagree
                  about what `base' means.

  paths.py        Filesystem layout: where the sidecar lives, how
                  base snapshots and conflict dirs are addressed,
                  the regex hardenings that keep user-supplied
                  strings out of path components.

  lock.py         Advisory exclusive flock on `<sidecar>/lock'.
                  Held by every mutating command for the duration of
                  its state mutation. Why on the sidecar and not on
                  FILE itself: atomic replace swaps FILE's inode.

  atomic_write.py The canonical write ritual:
                    tmp -> fsync -> rename -> fsync(parent).
                  All file content updates go through this.

  store.py        Sidecar persistence -- `state.json' read/write and
                  base snapshot storage. Pure functions over a held
                  lock; never acquires the lock itself.

  merge.py        POSIX `diff3 -m' wrapper. Argument order is the
                  one classical pitfall (PROPOSED BASE CURRENT, in
                  that order). `diff3' missing or broken is a tool
                  error, NEVER a content conflict (P10).

  cli.py          argparse + dispatch + JSON envelope. The thinnest
                  layer between the user's terminal and the command
                  implementations under commands/. Also handles the
                  one special case (`cat-base' streams raw bytes,
                  bypassing the JSON envelope).

  commands/       One file per CLI subcommand. Each `cmd_*' returns
                  a dict that becomes the JSON envelope; raises a
                  `CotypeError' for any failure path.

  __main__.py     Allows `python -m cotype ...' as well as the
                  installed `cotype' console script.

Properties P1-P15 mentioned in docstrings are defined in
`kb/properties/functional.md' (in the source repo, not shipped with
the wheel). They are the testable invariants the implementation
upholds.
"""
__version__ = "0.2.2"
