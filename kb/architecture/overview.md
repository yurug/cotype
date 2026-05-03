---
id: architecture-overview
type: concept
summary: Module structure, dependency graph, and error hierarchy for the Python implementation.
domain: architecture
last-updated: 2026-05-02
depends-on: [spec-algorithms, spec-error-taxonomy]
refines: []
related: [conventions-code-style, conventions-error-handling, adr-0001, adr-0002, adr-0003]
---

# Architecture overview

## One-liner
Small Python package, layered: pure helpers → IO primitives → store → commands → CLI.

## Module map

```
stile/
  __init__.py           # version constant
  __main__.py           # python -m stile -> cli.main()
  cli.py                # argparse wiring + dispatch + JSON envelope
  errors.py             # StileError hierarchy + name <-> exit-code table
  hash.py               # H(b) -> "sha256:<hex>"; helpers to split/validate
  paths.py              # FILE -> sidecar paths; relative-path helpers; sidecar validation
  lock.py               # contextmanager: flock(LOCK_EX) on <sidecar>/lock
  atomic_write.py       # atomic_replace(target, bytes) per algorithms.md
  store.py              # state.json read/write; store_base; create_conflict_dir
  merge.py              # merge3(base, current, proposed) -> Clean|Conflict|ToolError
  commands/
    __init__.py
    init.py             # cmd_init(args) -> dict
    open_.py            # cmd_open(args)
    save.py             # cmd_save(args)
    status.py           # cmd_status(args)
    resolve.py          # cmd_resolve(args)
tests/
  conftest.py
  test_hash.py
  test_paths.py
  test_atomic_write.py
  test_store.py
  test_merge.py
  test_init.py
  test_open.py
  test_save.py
  test_save_merge.py
  test_save_conflict.py
  test_status.py
  test_resolve.py
  test_T10_atomicity.py     # threaded smoke test
  test_security.py          # actor injection, path traversal, etc.
pyproject.toml
README.md
```

## Dependency graph

```
cli ──┬──> commands/* ──> store ──┬──> hash, paths, atomic_write, lock
      │                           └──> merge ──> (subprocess) diff3
      └──> errors

(All modules import errors. paths and hash are leaf modules.)
```

Rules:
- `errors`, `hash`, `paths` are leaves (no inter-module imports).
- `lock`, `atomic_write` may import `paths`, `errors`.
- `store` may import `lock`, `atomic_write`, `hash`, `paths`, `errors`.
- `merge` is independent except for `errors`.
- `commands/*` orchestrate everything below; they DO NOT import each other.
- `cli` imports `commands/*` and `errors` only.

## Error hierarchy

```
StileError(Exception)
 ├── UsageError                # exit 2
 ├── UnsupportedFile           # exit 3
 ├── UnmanagedFile             # exit 3
 ├── CorruptSidecar            # exit 3
 ├── UnknownBase               # exit 4
 ├── ConflictPending           # exit 5
 ├── ConflictIdMismatch        # exit 2
 ├── IoError                   # exit 6
 ├── MergeToolError            # exit 7
 └── InvalidUtf8               # exit 3
```

Each subclass has a class attribute `name` (matches the JSON `error` field) and `exit_code`.

## Dispatch flow

```
cli.main(argv)
  parse args (argparse)
  resolve realpath
  select cmd_<name>
  try:
      result_dict = cmd_<name>(args)
      emit_success(result_dict, json=args.json)
      return 0
  except StileError as e:
      emit_error(e, json=args.json)
      return e.exit_code
  except OSError as e:
      emit_error(IoError(str(e)), json=args.json)
      return 6
```

No `except Exception`; uncaught is a bug, let Python print the traceback.

## Key design decisions (links)

- `decisions/0001-python-stdlib-only.md` — language and dependency stance.
- `decisions/0002-diff3-for-merge.md` — using POSIX `diff3 -m` instead of an internal merger.
- `decisions/0003-sidecar-flock.md` — flock on sidecar/lock, not on FILE.

## Agent notes
> Commands return plain `dict` payloads; the CLI layer turns them into JSON. Never let a command call `print()` directly — kills testability.
> The lock is acquired by commands (top of the call chain), not by `store.py`. Lower layers assume the caller holds it.
> Subprocess invocations of `diff3` use the LIST form (`subprocess.run([...])`), never the shell form. See P-path-traversal-safety / T19.

## Related files
- `decisions/` — ADRs
- `../conventions/code-style.md` — style + size limits
- `../conventions/error-handling.md` — how/where to raise
- `../external/diff3.md` — the subprocess we depend on
