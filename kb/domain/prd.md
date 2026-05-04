---
id: prd
type: spec
summary: Authoritative product requirements for stile -- what it is, who uses it, what it must and must not do.
domain: product
last-updated: 2026-05-03
depends-on: [glossary]
refines: []
related: [spec-algorithms, properties-functional]
---

# PRD: stile

## 1. Summary

`stile` is a small, editor-agnostic command-line tool that prevents lost updates when a text file is modified concurrently by a human and one or more processes — typically AI agents.

The primary use case is a **shared text file used as the communication medium between a user and one or more agents, in place of a sequential chat**. The user writes; agents read and edit the file in place to respond or to do work; `stile` keeps every actor's view consistent. Disjoint edits auto-merge. Overlapping edits surface as explicit conflicts that the user resolves. There is no chat transcript — the file *is* the workspace.

The product is intentionally simple:

```text
open  = capture the current file as a base snapshot
save  = serialize a proposed new version against that base
merge = use 3-way merge when the file changed meanwhile
fail  = make conflicts explicit, never overwrite silently
```

`stile` does not replace editors, Git, build systems, or CRDT collaboration tools. It gives any editor or process a safe synchronization point around ordinary text files.

## 2. Product principle

The core rule is:

```text
No actor writes the target file directly during managed operation.
Actors submit candidate file contents to stile.
stile either writes atomically, merges safely, or rejects with a conflict.
```

This is the KISS version. The event-log/reducer design is deferred to a future version.

## 3. Problem

A common failure mode:

```text
T0: editor opens file.txt containing A
T1: process rewrites file.txt to B
T2: editor saves its buffer C, based on A
Result: B is silently lost
```

Existing tools partially help:

- Editors can warn that a file changed on disk.
- `flock` can serialize cooperating processes.
- Git can merge, but is repository-oriented and too heavy for a single save operation.
- CRDT systems solve live collaboration, but require a different editing model.

There is no tiny, universal `safe save` protocol for a normal local text file.

## 4. Goals

`stile` must provide:

1. Safe concurrent saves for a single regular text file.
2. Editor-agnostic integration through CLI commands and stdin/stdout.
3. Process integration with the same protocol as editors.
4. No silent overwrites when the base is stale.
5. Atomic replacement of the target file.
6. Explicit conflict output when 3-way merge cannot produce a clean result.
7. Minimal sidecar storage next to the file.

## 5. Non-goals

`stile` must not implement:

- Network synchronization.
- Multi-user real-time collaboration.
- CRDTs.
- Append-only event sourcing.
- Semantic operations such as JSON path edits.
- Multi-file transactions.
- Full VCS history.
- Binary file support.
- Daemon mode.

## 6. Users

### Human editor user

A user edits `file.txt` in Emacs, Vim, VS Code, or another editor. The editor integration calls `stile open` when loading and `stile save` when saving.

### AI agent

An LLM-driven assistant, code generator, reviewer, or other automated worker reads `file.txt` to understand context and writes back to share results, ask follow-ups, or annotate the user's text. It uses the same `open`/`save` flow as a human editor — there is no privileged path.

### Process writer

A script, formatter, build hook, or long-running service that computes a new version of `file.txt`. Same protocol again: `open` to capture the base, then `save` to submit a candidate.

### Tool author

An editor plugin author or agent harness author needs a tiny protocol with precise return codes and JSON output.

## 7. Core user stories

### US0: Shared file as the substrate for human-agent collaboration (primary)

A user and one or more agents collaborate by editing a single text file together — for example, `task.md`, `chat.md`, or any document where instructions, replies, code blocks, and review notes accumulate in place.

```text
T0  user opens task.md, writes a question.
T1  agent A runs `stile open task.md`, reads from base_path, computes a reply,
    writes it inline under the question, runs `stile save`. mode = direct.
T2  user reads the agent's reply, types a follow-up, saves through stile.
    mode = direct.
T3  agent B (a different worker) is also running. It opens task.md, edits a
    different section, saves. The user's edit and agent B's edit don't
    overlap -- mode = merged.
T4  user and agent A both edit the same section at once. stile refuses to
    silently pick a winner. mode = conflict; FILE is rewritten with diff3
    markers; the user edits them out and runs `stile resolve` to clear
    the pending state. Agents idle while the conflict is pending.
```

The file is a persistent, version-controllable workspace that the user can read, edit, and redirect at any moment. Multiple agents can act in parallel without a central UI. `stile` is what makes the whole pattern safe.

### US1: Direct save when no one else changed the file

Given `file.txt` contains `A`, and the editor opened base `A`, when the editor saves `C`, `stile` writes `C` atomically.

### US2: Auto-merge when another actor changed disjoint lines

Given an editor opened base `A`, and a process saved `B`, when the editor saves `C`, `stile` computes a 3-way merge of `(base=A, current=B, proposed=C)`. If the edits are compatible, it writes the merged result.

### US3: Conflict instead of lost update

Given an editor opened base `A`, and a process saved `B`, when the editor saves conflicting `C`, `stile` must not silently choose between `B` and `C`. It rewrites `file.txt` with diff3 markers spanning both versions, sets a pending-conflict state, and writes forensic artifacts. Subsequent saves are rejected with `ConflictPending` until the user edits out the markers and runs `stile resolve`.

### US4: Same protocol for humans and processes

A process must use exactly the same `open` and `save` flow as an editor. There is no privileged writer other than `stile` itself.

## 8. CLI UX

### Initialize

```bash
stile init file.txt
```

Creates sidecar storage:

```text
.file.txt.stile/
  lock
  state.json
  bases/
  conflicts/
  tmp/
```

### Open

```bash
stile open file.txt --json
```

Captures the current file content as a base snapshot and returns metadata:

```json
{
  "status": "ok",
  "file": "file.txt",
  "base_sha": "sha256:...",
  "base_path": ".file.txt.stile/bases/...",
  "conflicted": false
}
```

Safe editor integrations should load the buffer from `base_path`, not by separately reading `file.txt` after `open`.

### Save

```bash
stile save file.txt --base-sha sha256:... --actor emacs < new-content.txt
```

Possible results:

```json
{"status":"saved","mode":"direct","sha":"sha256:..."}
{"status":"saved","mode":"merged","sha":"sha256:..."}
{"status":"saved","mode":"noop","sha":"sha256:..."}
{"status":"conflict","conflict_id":"...","conflict_path":"..."}
```

### Status

```bash
stile status file.txt --json
```

Returns whether the file is managed, its current hash, and whether a conflict is pending.

### Resolve conflict

```bash
stile resolve file.txt --actor user
```

When `stile save` produces a conflict, `file.txt` is rewritten in place
with diff3 markers (`<<<<<<<` / `=======` / `>>>>>>>`). The user opens
`file.txt` in their editor, removes the markers, saves the buffer, and
runs `stile resolve file.txt` to clear the pending conflict. `resolve`
refuses if any markers are still present.

## 9. Editor integration contract

A correct editor integration does this:

```text
on file load:
  run stile open FILE --json
  load buffer from returned base_path
  remember base_sha

on save:
  send current buffer to stile save FILE --base-sha BASE_SHA --actor EDITOR
  if status = saved:
    reload buffer from FILE or use returned content if provided
    set BASE_SHA to returned sha
    mark buffer clean
  if status = conflict:
    show conflict_path to the user
    keep buffer dirty or enter conflict workflow
```

The editor must not write `FILE` directly while the file is under `stile` management.

## 10. Process integration contract

A process that wants to modify `file.txt` does this:

```bash
meta=$(stile open file.txt --json)
base_sha=$(printf '%s' "$meta" | jq -r .base_sha)
base_path=$(printf '%s' "$meta" | jq -r .base_path)

my-generator < "$base_path" > /tmp/new-file.txt

stile save file.txt \
  --base-sha "$base_sha" \
  --actor my-generator \
  < /tmp/new-file.txt
```

The process must not use direct writes to `file.txt`.

## 11. Product invariants

### I1: No silent stale overwrite

If the current file hash differs from the caller's base hash, `stile save` must either perform a successful 3-way merge or report a conflict. It must not directly replace the current file with the proposed content.

### I2: Atomic visibility

Readers of `file.txt` must observe either the old complete file or the new complete file, never a partial write.

### I3: Sidecar snapshots are auxiliary

Base snapshots enable 3-way merge. The target file remains a normal file. `stile` is not an event-sourced system.

### I4: Conflicts are explicit

On conflict, `stile save` rewrites `file.txt` with diff3 markers (`<<<<<<<` / `=======` / `>>>>>>>`) — both sides preserved verbatim — and records a pending-conflict state in the sidecar. Until the user edits out the markers and runs `stile resolve`, every subsequent `stile save` is rejected with `ConflictPending`. A forensic copy of the three sides (`base`, `current`, `proposed`, `merged`) is kept under `<sidecar>/conflicts/<id>/` for diagnostics.

## 12. MVP scope

Required commands:

```text
init
open
save
status
resolve
```

Optional commands:

```text
cat-base
clean
version
```

Do not implement anything else before the core invariants are tested.

## 13. Acceptance criteria

### AC1: Direct save

Given a file with content `A`, after `open` and `save` with proposed content `B`, the file contains `B` and exit code is 0.

### AC2: Stale compatible save

Given base `A`, current file `B`, and proposed `C` with disjoint edits from `A`, `save` writes a clean merge and returns mode `merged`.

### AC3: Stale conflicting save

Given base `A`, current file `B`, and proposed `C` with overlapping incompatible edits, `save` exits with conflict code, leaves the file at `B`, and writes conflict artifacts.

### AC4: No partial writes

A test that repeatedly reads the target file while `stile save` writes large content must never observe truncated or mixed content.

### AC5: Unknown base rejection

`save --base-sha H` must reject if no base snapshot for `H` exists.

### AC6: Pending conflict rejection

If a conflict is pending, ordinary `save` must reject until `resolve` succeeds.

### AC7: Same protocol for process and editor

A script using only `open` and `save` must get the same correctness properties as an editor plugin.

## 14. Future work (out of scope)

Possible future versions:

- Event log plus reducer mode.
- Per-file history and checkout.
- Semantic operations for JSON, YAML, Markdown sections, or domain-specific files.
- Multi-file transaction support.
- Watch mode or daemon mode.
- Editor plugins.
- Integration with Git or Jujutsu.

## 15. Product positioning

The simplest accurate name is:

```text
stile: universal safe-save for concurrent text files
```

The tool succeeds if it is boring, predictable, and small.

## Agent notes
> This is the canonical PRD. Where this disagrees with `spec/` files, defer to `spec/` on normative behaviour and update this file to match.
> The "Non-goals" list (§5) is load-bearing -- refuse scope creep that pushes any of those items into the product.

## Related files
- `../spec/INDEX.md` -- normative behaviour, decomposed for agent navigation
- `../properties/functional.md` -- the invariants in §11 expressed as P1..P15
- `../properties/edge-cases.md` -- the acceptance criteria in §13 expressed as T1..T22
