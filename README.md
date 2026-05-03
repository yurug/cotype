# stile

> A shared text file as the medium between you and your agents — kept consistent.

`stile` is a small CLI that lets a user and one or more AI agents (or any other
processes) collaborate on the **same text file at the same time** without losing
anyone's edits. The file is the workspace; `stile` is what makes every save safe.

```text
open  = capture the current file as a base snapshot
save  = serialize a proposed new version against that base
merge = 3-way merge when the file changed meanwhile
fail  = make conflicts explicit, never overwrite silently
```

## Use case: a file as the conversation

Instead of a sequential chat, point your agent at a shared file. The user
writes; the agent reads and edits in place to respond, ask, or do work. Any
number of agents can run in parallel — each goes through `stile open` →
compute → `stile save`. `stile` decides per save whether it's a clean direct
write, an auto-merge of disjoint edits, or a conflict the user must resolve.

A typical session on `task.md`:

```markdown
# Refactor the auth module

## user
Look at src/auth.py and tell me what's brittle.

## agent (review)            <-- agent appended this section, stile saved
Three things stand out:
1. session token written to disk in plaintext
2. retry loop has no backoff
3. logout clears the session map without locking

What would you like me to fix first?

## user                      <-- user typed this, stile saved
Fix #1.

## agent (status)            <-- agent appended this section in parallel
Wrote PR #42 against src/auth.py. Diff:
   ...
```

While the user types under `## user`, the agent can edit `## agent (status)`
in parallel. Disjoint sections → `stile` auto-merges. Same section, both
sides → `stile` conflicts and dumps the three versions for the user to settle.
No actor ever silently overwrites another.

The same machinery serves any "shared file" workflow — design docs, todo
lists, generated artifacts a formatter rewrites while a human edits. The
agent collaboration scenario is just the most direct demonstration.

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

Capture a fresh base snapshot. Returns `base_sha` and `base_path` — every safe
caller (human, agent, process) loads its working copy from `base_path`, not by
re-reading FILE.

```bash
$ stile open task.md --json
{
  "status": "ok",
  "file": "/path/to/task.md",
  "base_sha": "sha256:...",
  "base_path": ".task.md.stile/bases/...",
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

`--actor` is a free-form label (e.g. `emacs`, `agent:reviewer`,
`agent:formatter`, `me`). Stored in the conflict metadata; never affects
semantics. There is no privileged actor — every caller plays by the same rules.

### `stile status FILE [--json]`

Report whether the file is `unmanaged`, `clean`, or `conflicted`.

### `stile resolve FILE --conflict-id ID [--actor ACTOR] [--json] < resolved`

Accept a tool/human-provided resolution; clears the pending conflict.

## Caller protocols

### Editor

```text
on file load:
  response = stile open FILE --json
  buffer   = read(response.base_path)
  base_sha = response.base_sha

on save:
  response = stile save FILE --base-sha base_sha --actor emacs < buffer
  case response.status:
    saved    -> base_sha = response.sha
    conflict -> show response.conflict_path; do not mark buffer clean
```

### Agent / process

```bash
meta=$(stile open task.md --json)
base_sha=$(printf '%s' "$meta" | jq -r .base_sha)
base_path=$(printf '%s' "$meta" | jq -r .base_path)

my-agent < "$base_path" > /tmp/proposed
stile save task.md --base-sha "$base_sha" --actor agent:reviewer < /tmp/proposed
```

The agent **always** reads from `base_path`, never from `FILE` directly —
otherwise a concurrent writer's bytes can sneak into the agent's "what I edited
from" without `stile` noticing. See `kb/spec/protocols.md` for the normative
form and the forbidden pattern that loses updates.

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

v0 supports regular UTF-8 text files only. Out of scope: network sync,
multi-user real-time collaboration over a wire, CRDTs, event sourcing,
semantic edits, multi-file transactions, daemon / watch mode, binary files.
The full PRD lives at `kb/domain/prd.md`.

## Tests

```bash
pip install pytest
pytest -q
```

## License

MIT.
