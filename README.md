# stile

> Universal safe-save for concurrent text files.

`stile` prevents lost updates when a text file is edited concurrently by a human
editor and one or more processes. It is editor-agnostic: any tool that can run
a CLI and pipe stdin can be a safe writer.

```text
open  = capture the current file as a base snapshot
save  = serialize a proposed new version against that base
merge = use 3-way merge when the file changed meanwhile
fail  = make conflicts explicit, never overwrite silently
```

## Install

Requires **Python ≥3.11** and **POSIX `diff3`** (from `diffutils`).

```bash
# from a clone
pip install -e .

# verify
stile --help
```

## Commands

### `stile init FILE [--json]`

Initialise the sidecar directory `.<basename>.stile/` next to FILE and store the
current contents as the first base snapshot.

### `stile open FILE [--json]`

Capture a fresh base snapshot. Returns `base_sha` and `base_path` — load your
editor buffer from `base_path` (not from FILE again) for race-free integration.

```bash
$ stile open notes.txt --json
{
  "status": "ok",
  "file": "/path/to/notes.txt",
  "base_sha": "sha256:...",
  "base_path": ".notes.txt.stile/bases/...",
  "conflicted": false
}
```

### `stile save FILE --base-sha HASH [--actor ACTOR] [--json] < proposed`

Submit candidate content. Outcomes:

| `mode`   | meaning                                                       |
|----------|---------------------------------------------------------------|
| `direct` | base matched current; proposed written atomically             |
| `merged` | 3-way merge produced a clean result; merged content written   |
| `noop`   | proposed equals current; nothing to do                        |

A conflict yields `status: "conflict"`, exit code `1`, and a forensic dump under
`.<basename>.stile/conflicts/<id>/`.

### `stile status FILE [--json]`

Report whether the file is `unmanaged`, `clean`, or `conflicted`.

### `stile resolve FILE --conflict-id ID [--actor ACTOR] [--json] < resolved`

Accept a tool/human-provided resolution; clears the pending conflict.

## Editor protocol

```text
on file load:
  response = stile open FILE --json
  buffer   = read(response.base_path)
  base_sha = response.base_sha

on save:
  response = stile save FILE --base-sha base_sha < buffer
  case response.status:
    saved    -> base_sha = response.sha
    conflict -> show response.conflict_path; do not mark buffer clean
```

## Process protocol

```bash
meta=$(stile open file.txt --json)
base_sha=$(printf '%s' "$meta" | jq -r .base_sha)
base_path=$(printf '%s' "$meta" | jq -r .base_path)

my-formatter < "$base_path" > /tmp/new
stile save file.txt --base-sha "$base_sha" --actor my-formatter < /tmp/new
```

## Exit codes

| Code | Meaning                       |
|------|-------------------------------|
| 0    | success                       |
| 1    | merge conflict                |
| 2    | usage error                   |
| 3    | unmanaged or corrupt sidecar  |
| 4    | unknown base                  |
| 5    | pending conflict              |
| 6    | I/O error                     |
| 7    | merge tool error              |

## Stable error names

`UsageError`, `UnsupportedFile`, `UnmanagedFile`, `CorruptSidecar`,
`UnknownBase`, `ConflictPending`, `ConflictIdMismatch`, `IoError`,
`MergeToolError`, `InvalidUtf8`. JSON shape:

```json
{ "status": "error", "error": "<Name>", "message": "<detail>" }
```

## Scope

v0 supports regular UTF-8 text files only. Out of scope: network sync, multi-user
real-time collaboration, CRDTs, event sourcing, semantic edits, multi-file
transactions, daemon mode, binary files. See `kb/domain/prd.md`.

## Tests

```bash
pip install pytest
pytest -q
```

## License

MIT.
