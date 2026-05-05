# cotype — CLI reference

Universal safe-save for concurrent text files. The Python implementation
that gets installed by editor integrations and agent harnesses.

For the user-facing pitch, the demo, and the quick start, see the
[monorepo top-level README](../README.md). This document is the
technical reference: every command, flag, exit code, and the protocols
callers must follow.

## Install

```bash
pip install cotype
```

Requires **Python ≥ 3.11** and **POSIX `diff3`** (from `diffutils`).

For development from a clone:

```bash
git clone https://github.com/yurug/cotype.git
cd cotype
pip install -e cli/
```

## CLI surface

```text
cotype init     FILE [--json]
cotype open     FILE [--json]
cotype save     FILE --base-sha HASH [--actor ACTOR] [--json] < proposed
cotype status   FILE [--json]
cotype resolve  FILE [--actor ACTOR] [--json]
cotype cat-base FILE [--base-sha HASH]
```

| Command | What it does |
|---|---|
| `cotype init` | Start managing FILE: create the sidecar (`.<basename>.cotype/`) and capture the current contents as the first base snapshot. Idempotent. |
| `cotype open` | Capture a fresh base snapshot before you (or your agent) edit. Returns `base_sha` and a `base_path` to read the bytes from. |
| `cotype save` | Submit a proposed new version (stdin) against `--base-sha`. Outcome is `direct` / `merged` / `noop` / `conflict`. |
| `cotype status` | Report whether FILE is `unmanaged`, `clean`, or `conflicted`. Side-effect free; safe to poll. |
| `cotype resolve` | Clear a pending conflict by accepting FILE's current contents (after the user has edited out the diff3 markers). |
| `cotype cat-base` | Print a base snapshot's bytes to stdout. Useful in shell pipelines. |

`cotype --help` and `cotype <subcommand> --help` give the full per-command
descriptions plus a copy-pasteable shell template; that's the canonical
agent-discoverable surface.

## `save` outcomes

| `mode` | meaning |
|---|---|
| `direct` | base matched current; proposed bytes written atomically. |
| `merged` | 3-way merge produced a clean result; merged content written. |
| `noop` | proposed equals current; nothing to do. |

A **conflict** yields `status: "conflict"`, exit code `1`, and rewrites
FILE in place with diff3 markers (`<<<<<<<` / `=======` / `>>>>>>>`).
Open FILE in your editor, remove the markers, save, then run
`cotype resolve FILE`. A forensic copy of the three sides is kept under
`.<basename>.cotype/conflicts/<id>/` for diagnostics. Until `resolve` is
called, every `cotype save` returns `ConflictPending`.

`--actor` is a free-form label (e.g. `emacs`, `agent:reviewer`,
`agent:formatter`, `me`). Stored in the conflict metadata; never affects
semantics. There is no privileged actor — every caller plays by the same
rules.

## Caller protocols

### Editor

```text
on file load:
  response = cotype open FILE --json
  buffer   = read(response.base_path)
  base_sha = response.base_sha

on save:
  response = cotype save FILE --base-sha base_sha --actor emacs < buffer
  case response.status:
    saved    -> base_sha = response.sha
    conflict -> show response.conflict_path; do not mark buffer clean
```

### Agent / process

```bash
meta=$(cotype open task.md --json)
base_sha=$(printf '%s' "$meta" | jq -r .base_sha)
base_path=$(printf '%s' "$meta" | jq -r .base_path)

my-agent < "$base_path" > /tmp/proposed
cotype save task.md --base-sha "$base_sha" --actor agent:reviewer < /tmp/proposed
```

The agent **always** reads from `base_path`, never from `FILE` directly —
otherwise a concurrent writer's bytes can sneak into the agent's "what I
edited from" without `cotype` noticing. The normative form and the
forbidden pattern that loses updates are at
[`../kb/spec/protocols.md`](../kb/spec/protocols.md).

## Exit codes

| Code | Meaning |
|---|---|
| 0 | success |
| 1 | merge conflict |
| 2 | usage error |
| 3 | unmanaged or corrupt sidecar |
| 4 | unknown base |
| 5 | pending conflict |
| 6 | I/O error |
| 7 | merge tool error |

## Stable error names

`UsageError`, `UnsupportedFile`, `UnmanagedFile`, `CorruptSidecar`,
`UnknownBase`, `ConflictPending`, `IoError`, `MergeToolError`,
`InvalidUtf8`. JSON shape (with `--json`):

```json
{ "status": "error", "error": "<Name>", "message": "<detail>" }
```

## Reducing false-positive conflicts

cotype's merge is line-based (POSIX `diff3`); independent edits within
the same hunk can spuriously conflict. Two cheap mitigations:

1. **Pad region boundaries.** Diff3 needs ~2 unchanged lines between two
   edit zones to treat them as separate hunks. Insert blank lines or a
   stable sentinel comment between regions different actors own.
2. **Splice structurally in the harness.** Parse the file into regions
   (Markdown sections, top-level defs, JSON keys) and rewrite ONLY your
   own region's bytes; everything else flows through unchanged from
   `base_path`. Two actors editing two different regions then cannot
   conflict by construction. See [`../examples/headless-agents.sh`](../examples/headless-agents.sh)
   for the reference Markdown recipe.

## Architecture (one paragraph)

Pure leaves (`hash`, `paths`, `errors`), I/O primitives (`lock`,
`atomic_write`), persistence (`store`), the merge wrapper (`merge`),
command implementations under `commands/`, and a single `cli.py` that
wires argparse and the JSON envelope. Every mutating command holds an
exclusive `flock` on `<sidecar>/lock`; every file replacement goes
through tmp → fsync → rename → fsync(parent). 3-way merge invokes POSIX
`diff3 -m` in subprocess (list form, never shell). Public functions are
typed; files are under 200 lines; the test suite covers SPEC §14
conformance (T1–T10), every named property (P1–P15), security edges,
and a threaded atomic-visibility smoke test.

For the "why" behind these choices, see
[`../kb/architecture/decisions/`](../kb/architecture/decisions/).

## Tests

```bash
cd cli
pip install pytest
pytest -q
```
