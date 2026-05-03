---
id: spec-api-contracts
type: spec
summary: CLI inputs and JSON output shapes for every stile command.
domain: spec
last-updated: 2026-05-02
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

## `stile init FILE [--json]`

Output (success, `--json`):
```json
{ "status": "ok", "file": "file.txt", "sha": "sha256:...", "sidecar": ".file.txt.stile" }
```
Exit: 0 on success. See error taxonomy for all reject paths.

## `stile open FILE [--json]`

Output (success, `--json`, no pending conflict):
```json
{
  "status": "ok",
  "file": "file.txt",
  "base_sha": "sha256:...",
  "base_path": ".file.txt.stile/bases/<hex>",
  "conflicted": false
}
```
Output when a conflict is pending:
```json
{
  "status": "ok",
  "file": "file.txt",
  "base_sha": "sha256:...",
  "base_path": ".file.txt.stile/bases/<hex>",
  "conflicted": true,
  "pending_conflict": { "id": "...", "path": ".file.txt.stile/conflicts/<id>" }
}
```
Exit: 0.

## `stile save FILE --base-sha HASH [--actor ACTOR] [--json] < PROPOSED`

Success:
```json
{ "status": "saved", "mode": "<direct|merged|noop>", "sha": "sha256:..." }
```
Conflict:
```json
{
  "status": "conflict",
  "conflict_id": "...",
  "conflict_path": ".file.txt.stile/conflicts/<id>",
  "base_sha": "sha256:...",
  "current_sha": "sha256:...",
  "proposed_sha": "sha256:..."
}
```
Exit: 0 saved · 1 conflict · 4 unknown base · 5 pending conflict · 7 merge tool error · 3 corrupt/unmanaged · 2 usage · 6 io.

## `stile status FILE [--json]`

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
  "pending_conflict": { "id": "...", "path": ".file.txt.stile/conflicts/<id>" }
}
```
Unmanaged:
```json
{ "status": "unmanaged", "file": "file.txt" }
```
Exit: 0 in all three states. (`status` is reporting; not a failure.)

## `stile resolve FILE --conflict-id ID [--actor ACTOR] [--json] < RESOLVED`

```json
{ "status": "resolved", "file": "file.txt", "sha": "sha256:..." }
```
Exit: 0 success · 2 usage (no pending conflict, id mismatch) · 3 corrupt/unmanaged · 6 io.

## Error envelope

Every error in `--json` mode emits to **stdout**:
```json
{ "status": "error", "error": "<StableName>", "message": "<human prose>" }
```
Without `--json`, a one-line message goes to **stderr**. Exit code is set per `spec/error-taxonomy.md`.

## Stdin handling

- `save` and `resolve` consume stdin to EOF. Read as raw bytes; UTF-8 decode for validation only.
- A closed/empty stdin is a legitimate "empty proposed content" — hash is `H(b"")`. Not an error.

## Agent notes
> The conflict envelope is asymmetric: success returns `mode`, conflict returns `conflict_id` + per-side hashes. Don't conflate them in client code.
> `--json` is the supported integration surface. Human strings are NOT a contract — do not parse them.
> Stdin is bytes; decode for validation, hash the bytes, write the bytes (no re-encoding).

## Related files
- `spec/algorithms.md` — what each command does
- `spec/error-taxonomy.md` — every error name + exit code
- `spec/config-and-formats.md` — sidecar file formats
