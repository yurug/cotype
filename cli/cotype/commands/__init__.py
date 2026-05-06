"""Command implementations -- one file per `cotype <subcommand>'.

The contract every `cmd_*' function follows:

  - Takes parsed-argv-style arguments (strings, bytes for stdin
    payloads).
  - Returns a plain `dict' that becomes the success-side JSON
    envelope.
  - Raises a `CotypeError' subclass for any failure path. The CLI
    layer turns those into the error envelope + exit code.

Why the dict-not-print discipline: it makes the commands trivially
testable. `tests/test_*.py` calls `cmd_save(...)' directly and
asserts on the returned dict, no subprocess hop, no stdout capture.
A `cmd_*' that printed would defeat this -- and would also break
the JSON-envelope-on-stdout contract because the human-readable
fallback in `cli.py' would be racing the command's own prints.

Files in this package
=====================

  init.py     `cotype init'    -- create sidecar + capture first base.
  open_.py    `cotype open'    -- capture a fresh base; return base_sha + base_path.
  save.py     `cotype save'    -- the heart: branch into direct / merged / noop / conflict.
  status.py   `cotype status'  -- read-only state report.
  resolve.py  `cotype resolve' -- accept a hand-edited FILE as the conflict resolution.
  catbase.py  `cotype cat-base'-- stream a base snapshot's bytes to stdout.

(`open_' has the trailing underscore because `open' is a Python
builtin; the module name leaks into imports, so the underscore is
better than shadowing.)
"""
