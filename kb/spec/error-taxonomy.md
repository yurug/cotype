---
id: spec-error-taxonomy
type: spec
summary: Every stable error name, when it fires, exit code, and JSON payload.
domain: spec
last-updated: 2026-05-03
depends-on: [spec-data-model]
refines: []
related: [spec-algorithms, spec-api-contracts, conventions-error-handling]
---

# Error taxonomy

## One-liner
Stable JSON error names, the conditions that raise them, and their exit codes.

## Scope
Every named error. Implementation must use these strings verbatim — they are part of the integration contract.

## Exit codes (SPEC §9)

| Code | Meaning             |
|------|---------------------|
| 0    | success             |
| 1    | merge conflict      |
| 2    | usage error         |
| 3    | unmanaged or corrupt sidecar |
| 4    | unknown base        |
| 5    | pending conflict    |
| 6    | I/O error           |
| 7    | merge tool error    |

## Error names

| `error`              | Exit | Triggered when                                                                                  |
|----------------------|------|--------------------------------------------------------------------------------------------------|
| `UsageError`         | 2    | argparse failure; missing required arg; `resolve` called with no pending conflict; `resolve` called while FILE still contains diff3 conflict markers. |
| `UnsupportedFile`    | 3    | target is not a regular file (dir, symlink loop, fifo, socket, device); target missing for `init`. |
| `UnmanagedFile`      | 3    | sidecar absent and command requires it (`save`, `resolve`).                                      |
| `CorruptSidecar`     | 3    | `state.json` missing/malformed/unknown `format_version`; required sidecar subdir absent.         |
| `UnknownBase`        | 4    | `--base-sha HASH` given but `bases/<hex>` does not exist OR HASH is not a syntactically valid sha256 string. |
| `ConflictPending`    | 5    | `save` called while `state.pending_conflict != null`.                                            |
| `IoError`            | 6    | unexpected OS error (EIO, ENOSPC, EACCES on FILE, lock acquisition failure, etc.).               |
| `MergeToolError`     | 7    | `diff3` is missing, exits with status >=2, or its stderr indicates malfunction.                  |
| `InvalidUtf8`        | 3    | bytes (current, proposed, or resolved) fail UTF-8 decode.                                        |

## JSON envelope

```json
{ "status": "error", "error": "<Name>", "message": "<human-readable detail>" }
```

In `--json` mode this goes to **stdout**; otherwise the one-line `error: <Name>: <message>` form goes to **stderr**. Exit code as above.

## Examples

`save` against an absent base:
```json
{ "status": "error", "error": "UnknownBase",
  "message": "base snapshot sha256:abc...123 is not present" }
```
Exit 4.

`save` while a conflict is pending:
```json
{ "status": "error", "error": "ConflictPending",
  "message": "resolve conflict <id> first (see .file.txt.stile/conflicts/<id>)" }
```
Exit 5.

`diff3` missing:
```json
{ "status": "error", "error": "MergeToolError",
  "message": "diff3 not found on PATH; install diffutils" }
```
Exit 7.

## Agent notes
> Names are part of the contract. Renaming any of them is a breaking change.
> A `MergeToolError` MUST NOT be reported as a content conflict — see P10.
> Categorise OS errors strictly: an `EIO` writing the temp file is `IoError`, not `MergeToolError`.

## Related files
- `spec/api-contracts.md` — success envelopes for contrast
- `conventions/error-handling.md` — how the implementation should raise/translate
