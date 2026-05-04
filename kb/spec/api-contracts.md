---
id: spec-api-contracts
type: spec
summary: CLI inputs and JSON output shapes for every cotype command.
domain: spec
last-updated: 2026-05-03
depends-on: [spec-data-model, spec-error-taxonomy]
refines: [prd]
related: [spec-algorithms]
---

# API contracts

## One-liner
Inputs and outputs for every command. JSON payloads are the contract surface; human output is convenience.

## Scope
CLI surface only. Internal function signatures live in `architecture/overview.md`.

## Global flags

- `--json` — emit a JSON object on stdout (errors too); without it, emit a one-line human summary.
- `--actor STR` — opaque label, default `unknown`. Stored in conflict `meta.json`. Must not be run through a shell.

## `cotype init FILE [--json]`

Output (success, `--json`):
```json
{ "status": "ok", "file": "file.txt", "sha": "sha256:...", "sidecar": ".file.txt.cotype" }
```
Exit: 0 on success. See error taxonomy for all reject paths.

## `cotype open FILE [--json]`

Output (success, `--json`, no pending conflict):
```json
{
  "status": "ok",
  "file": "file.txt",
  "base_sha": "sha256:...",
  "base_path": ".file.txt.cotype/bases/<hex>",
  "conflicted": false
}
```
Output when a conflict is pending:
```json
{
  "status": "ok",
  "file": "file.txt",
  "base_sha": "sha256:...",
  "base_path": ".file.txt.cotype/bases/<hex>",
  "conflicted": true,
  "pending_conflict": { "id": "...", "path": ".file.txt.cotype/conflicts/<id>" }
}
```
Exit: 0.

## `cotype save FILE --base-sha HASH [--actor ACTOR] [--json] < PROPOSED`

Success:
```json
{ "status": "saved", "mode": "<direct|merged|noop>", "sha": "sha256:..." }
```
Conflict:
```json
{
  "status": "conflict",
  "conflict_id": "...",
  "conflict_path": ".file.txt.cotype/conflicts/<id>",
  "base_sha": "sha256:...",
  "current_sha": "sha256:...",
  "proposed_sha": "sha256:...",
  "markers_sha": "sha256:..."
}
```
On conflict, FILE is rewritten in place with the diff3 marker output (its SHA-256 is `markers_sha`). The sidecar still keeps a forensic copy at `<conflict_path>/{base, current, proposed, merged}` for diagnostics. `state.last_known_sha` becomes `markers_sha` and `state.pending_conflict` is set; further `save` calls return `ConflictPending` until `resolve` clears it.

Exit: 0 saved · 1 conflict · 4 unknown base · 5 pending conflict · 7 merge tool error · 3 corrupt/unmanaged · 2 usage · 6 io.

## `cotype status FILE [--json]`

Clean:
```json
{ "status": "clean", "file": "file.txt", "current_sha": "sha256:...", "last_known_sha": "sha256:..." }
```
Conflicted:
```json
{
  "status": "conflicted",
  "file": "file.txt",
  "current_sha": "sha256:...",
  "pending_conflict": { "id": "...", "path": ".file.txt.cotype/conflicts/<id>" }
}
```
Unmanaged:
```json
{ "status": "unmanaged", "file": "file.txt" }
```
Exit: 0 in all three states. (`status` is reporting; not a failure.)

## `cotype resolve FILE [--actor ACTOR] [--json]`

Reads FILE off disk and accepts it as the resolution: snapshots the bytes as a new base, sets `state.last_known_sha`, and clears `state.pending_conflict`. Refuses with `UsageError` if a `<<<<<<< ` opener and a `>>>>>>> ` closer line are both present (diff3 markers still in place — the user has not finished resolving). Refuses with `UsageError` when no conflict is pending. Reads no stdin.

Output:

```json
{ "status": "resolved", "file": "file.txt", "sha": "sha256:..." }
```
Exit: 0 success · 2 usage (no pending conflict, markers still present) · 3 corrupt/unmanaged/invalid-utf8 · 6 io.

## `cotype cat-base FILE [--base-sha HASH]`

Read-only utility: writes the bytes of a base snapshot to stdout. With no
`--base-sha`, uses `state.last_known_sha` (the most recently captured base).

Output: raw bytes of the requested base, on stdout. **No JSON envelope on
success** — this command intentionally does not accept `--json`, because
mixing JSON metadata with the bytes payload on the same stream would be
unparseable. Errors go to stderr in the standard `error: <Name>: <message>`
form, exit code per the table below.

Exit: 0 success · 3 unmanaged · 4 unknown base · 6 io.

Typical use (agent shell pipeline):
```bash
meta=$(cotype open task.md --json)
sha=$(printf '%s' "$meta" | jq -r .base_sha)
cotype cat-base task.md --base-sha "$sha" | my-agent | \
  cotype save task.md --base-sha "$sha" --actor agent:reviewer
```

## Error envelope

Every error in `--json` mode emits to **stdout**:
```json
{ "status": "error", "error": "<StableName>", "message": "<human prose>" }
```
Without `--json`, a one-line message goes to **stderr**. Exit code is set per `spec/error-taxonomy.md`.

## Stdin handling

- `save` consumes stdin to EOF. Read as raw bytes; UTF-8 decode for validation only.
- A closed/empty stdin is a legitimate "empty proposed content" — hash is `H(b"")`. Not an error.
- `resolve` does NOT read stdin (it reads FILE itself).

## Agent notes
> The conflict envelope is asymmetric: success returns `mode`, conflict returns `conflict_id` + per-side hashes. Don't conflate them in client code.
> `--json` is the supported integration surface. Human strings are NOT a contract — do not parse them.
> Stdin is bytes; decode for validation, hash the bytes, write the bytes (no re-encoding).

## Related files
- `spec/algorithms.md` — what each command does
- `spec/error-taxonomy.md` — every error name + exit code
- `spec/config-and-formats.md` — sidecar file formats
