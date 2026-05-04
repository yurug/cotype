# stile

[![tests](https://github.com/yurug/stile/actions/workflows/test.yml/badge.svg)](https://github.com/yurug/stile/actions/workflows/test.yml)

> A shared text file as a collaborative workspace — kept consistent.

`stile` is a small CLI that lets a user and one or more AI agents (or
any other processes) collaborate on the **same text file at the same
time** without losing anyone's edits. The file is the collaborative
workspace; `stile` is what makes every save safe.

`stile` is a very simple tool, essentially an extremely minimalistic `git`, but it
still allows the following 

<Inline the GIF of the demo here>


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

## Recipe: spawn N headless Claude agents on one file

The simplest "agents collaborate with you on a shared file" pattern is a
loop per role. Each agent polls, asks Claude for its take, and submits
through `stile save`. You edit `task.md` in any editor; `stile`'s 3-way
merge keeps everyone consistent.

```bash
# requires stile, claude (Claude Code CLI), and jq on PATH.
stile init task.md
for role in reviewer linter tester; do
  (
    while true; do
      meta=$(stile open task.md --json)
      base_sha=$(echo "$meta" | jq -r .base_sha)
      base_path=$(echo "$meta" | jq -r .base_path)
      # `claude --print -p PROMPT` ignores stdin -- splice the current
      # file content directly into the prompt.
      proposed=$(claude --print -p "You are agent:$role in a stile-managed
shared Markdown file. Edit your '## agent:$role' section in place to
respond to the user's latest input; output the entire file unchanged
otherwise.

<file>
$(cat "$base_path")
</file>")
      printf '%s' "$proposed" | stile save task.md \
        --base-sha "$base_sha" --actor "agent:$role" --json
      sleep 5
    done
  ) &
done
wait     # Ctrl-C to stop all agents
```

A polished, runnable version with cleanup, error handling, and per-role
PID tracking lives at
[`examples/headless-agents.sh`](examples/headless-agents.sh):

```bash
./examples/headless-agents.sh task.md reviewer linter tester
```

## Command description

A six-command tour:

| Command          | What it does                                                                                                                                                                                                              |
|------------------|---------------------------------------------------------------------------------------------------------------------------------------------------------------------------------------------------------------------------|
| `stile init`     | Start managing FILE: create the sidecar and capture the current contents as the first base snapshot.                                                                                                                      |
| `stile open`     | Capture a fresh base snapshot before you edit (or before your agent does). Returns `base_sha` and a `base_path` to read the bytes from.                                                                                   |
| `stile save`     | Submit a proposed new version against a base. Outcome is `direct` (clean write), `merged` (3-way merge), `noop` (proposed equals current), or `conflict` (overlapping edits — FILE is rewritten with `<<<<<<<` / `>>>>>>>` diff3 markers and a forensic dump is kept in the sidecar). |
| `stile status`   | Report whether FILE is `unmanaged`, `clean`, or `conflicted` (with the pending conflict id).                                                                                                                              |
| `stile resolve`  | Clear a pending conflict by accepting FILE's current contents. Edit FILE in your editor to remove the diff3 markers, then run `stile resolve FILE`.                                                                       |
| `stile cat-base` | Print a base snapshot's bytes to stdout (useful in shell pipelines: `stile cat-base FILE \| my-agent \| stile save FILE --base-sha …`).                                                                                   |

## Repository layout

This is a small monorepo: the CLI lives next to one self-contained folder per
editor mode. Each folder has its own README; the knowledge base at `kb/` is
shared by all of them.

| Path                                           | What lives there                                                                        |
|------------------------------------------------|-----------------------------------------------------------------------------------------|
| [`cli/`](cli/)                                 | The Python CLI implementation. `pip install -e cli/` to build.                          |
| [`editors/emacs/`](editors/emacs/)             | `stile-mode` minor mode for Emacs ≥ 27.1.                                               |
| [`examples/agent-loop/`](examples/agent-loop/) | Offline-runnable demo of the user-and-agents protocol.                                  |
| [`examples/demo/`](examples/demo/)             | 15-second scripted demo (VHS / asciinema) for social media.                             |
| [`kb/`](kb/)                                   | Agent-optimised knowledge base: PRD, normative spec, properties, ADRs, audit checklist. |

Future editor modes will land as siblings under `editors/` (`vim`, `vscode`, …).

## Install the CLI

Requires **Python ≥ 3.11** and **POSIX `diff3`** (from `diffutils`).

```bash
git clone https://github.com/yurug/stile.git
cd stile
pip install -e cli/

# verify
stile --help
```

## CLI surface (in one screen)

```text
stile init     FILE [--json]
stile open     FILE [--json]
stile save     FILE --base-sha HASH [--actor ACTOR] [--json] < proposed
stile status   FILE [--json]
stile resolve  FILE [--actor ACTOR] [--json]
stile cat-base FILE [--base-sha HASH]
```

`save` outcomes:

| `mode`   | meaning                                                     |
|----------|-------------------------------------------------------------|
| `direct` | base matched current; proposed written atomically           |
| `merged` | 3-way merge produced a clean result; merged content written |
| `noop`   | proposed equals current; nothing to do                      |

A conflict yields `status: "conflict"`, exit code `1`, and rewrites FILE
in place with diff3 markers (`<<<<<<<` / `=======` / `>>>>>>>`). Open
FILE in your editor, remove the markers, save, then run
`stile resolve FILE`. A forensic copy of the three sides is kept under
`.<basename>.stile/conflicts/<id>/` for diagnostics. Until `resolve` is
called, every `stile save` returns `ConflictPending`.

`--actor` is a free-form label (e.g. `emacs`, `agent:reviewer`,
`agent:formatter`, `me`). Stored in the conflict metadata; never affects
semantics. There is no privileged actor — every caller plays by the same rules.

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
otherwise a concurrent writer's bytes can sneak into the agent's "what I
edited from" without `stile` noticing. The normative form and the forbidden
pattern that loses updates are at [`kb/spec/protocols.md`](kb/spec/protocols.md).

## Exit codes

| Code | Meaning                      |
|------|------------------------------|
| 0    | success                      |
| 1    | merge conflict               |
| 2    | usage error                  |
| 3    | unmanaged or corrupt sidecar |
| 4    | unknown base                 |
| 5    | pending conflict             |
| 6    | I/O error                    |
| 7    | merge tool error             |

## Stable error names

`UsageError`, `UnsupportedFile`, `UnmanagedFile`, `CorruptSidecar`,
`UnknownBase`, `ConflictPending`, `IoError`,
`MergeToolError`, `InvalidUtf8`. JSON shape:

```json
{ "status": "error", "error": "<Name>", "message": "<detail>" }
```

## Why it's small

`stile` tries to be the smallest tool that can prevent lost updates: `open`,
`save`, and a 3-way merge when the base is stale. No daemon, no event
log, no CRDT, no network sync, no semantic edits, no multi-file
transactions. The PRD's non-goals list is load-bearing — `stile`
intentionally does *one* thing.

We want it to do one thing and do it right. 

## Tests

```bash
cd cli && pip install pytest && pytest -q
```

## License

MIT.
