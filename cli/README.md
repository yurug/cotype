# cotype (CLI)

The Python implementation of the `cotype` CLI — universal safe-save for
concurrent text files.

This is the package that gets installed by editor integrations and agent
drivers. The full product story (use case, KB, ADRs) lives at the
monorepo root.

## Install

Requires **Python ≥ 3.11** and **POSIX `diff3`** (from `diffutils`).

```bash
# from the monorepo root
pip install -e cli/

# verify
cotype --help
```

## Test

```bash
cd cli
pip install pytest
pytest -q
```

## Layout

```
cli/
├── pyproject.toml
├── cotype/                  the package
│   ├── __main__.py         python -m cotype
│   ├── cli.py              argparse + dispatch + JSON envelope
│   ├── errors.py           stable error names + exit codes
│   ├── hash.py             SHA-256 of raw bytes (P5 byte-exact)
│   ├── paths.py            sidecar resolution; conflict-id validation
│   ├── lock.py             advisory flock on <sidecar>/lock
│   ├── atomic_write.py     tmp -> fsync -> rename -> fsync(parent)
│   ├── store.py            state.json read/write, base storage
│   ├── merge.py            POSIX diff3 -m wrapper
│   └── commands/
│       ├── init.py
│       ├── open_.py
│       ├── save.py
│       ├── status.py
│       ├── resolve.py
│       └── catbase.py
└── tests/                  84 pytest tests
```

## Commands

```text
cotype init    FILE [--json]
cotype open    FILE [--json]
cotype save    FILE --base-sha HASH [--actor ACTOR] [--json] < proposed
cotype status  FILE [--json]
cotype resolve FILE [--conflict-id ID | --use-merged] [--actor ACTOR] [--json]
cotype cat-base FILE [--base-sha HASH]
```

Full surface, exit codes, and stable error names: see `../README.md` and
`../kb/spec/`.

## Architecture in one paragraph

A small layered package: pure leaves (`hash`, `paths`, `errors`), I/O
primitives (`lock`, `atomic_write`), persistence (`store`), the merge
wrapper (`merge`), command implementations under `commands/`, and a
single `cli.py` that wires argparse and the JSON envelope. Every
mutating command holds an exclusive flock on `<sidecar>/lock`; every
file replacement goes through the canonical
tmp → fsync → rename → fsync(parent) sequence. 3-way merge invokes
POSIX `diff3 -m` in subprocess (list form, never shell). All public
functions are typed; files are under 200 lines; the test suite covers
SPEC §14 conformance (T1–T10), every named property (P1–P15), security
edges, and a threaded atomic-visibility smoke test.

For the "why" behind these choices: `../kb/architecture/decisions/`.
