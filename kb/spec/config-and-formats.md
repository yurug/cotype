---
id: spec-config-and-formats
type: spec
summary: On-disk file formats — state.json, conflict meta.json, base storage.
domain: spec
last-updated: 2026-05-02
depends-on: [spec-data-model]
refines: []
related: [spec-algorithms]
---

# Config and on-disk formats

## One-liner
Schema of every file stile writes to disk. v0 has no user-editable config — only sidecar artifacts.

## Scope
File formats only. Algorithms in `spec/algorithms.md`. CLI shapes in `spec/api-contracts.md`.

## `state.json`

Encoding: UTF-8 JSON, pretty-printed (2-space indent, trailing newline). Must round-trip through `json.dumps(json.loads(...))`.

```json
{
  "format_version": 1,
  "target_path": "../file.txt",
  "last_known_sha": "sha256:...",
  "pending_conflict": null
}
```

Field rules:
- `format_version`: integer `1`. Anything else → `CorruptSidecar`.
- `target_path`: string, relative path from sidecar dir to FILE (informational; not used as authority).
- `last_known_sha`: hash string. Updated by every mutating command on success.
- `pending_conflict`: `null` OR object below.

Pending conflict object:
```json
{
  "id": "<32-hex-char uuid v4 with dashes stripped>",
  "base_sha": "sha256:...",
  "current_sha": "sha256:...",
  "proposed_sha": "sha256:...",
  "path": ".file.txt.stile/conflicts/<id>"
}
```

## `bases/<hex>`

Raw bytes — exactly the content that hashed to `<hex>`. No envelope, no header, no compression.

`<hex>` is the 64-char lowercase hex (the part of the hash after `sha256:`).

## `conflicts/<id>/`

Required files (each holds raw bytes; no envelope):
- `base` — the snapshot the actor was editing from.
- `current` — what was on disk when the conflict was detected.
- `proposed` — what the actor submitted.

Should-have:
- `merged` — output of `diff3 -m` including `<<<<<<<`/`=======`/`>>>>>>>` markers when applicable.

Required metadata (`meta.json`, UTF-8 JSON):
```json
{
  "id": "<conflict-id>",
  "actor": "<string>",
  "base_sha": "sha256:...",
  "current_sha": "sha256:...",
  "proposed_sha": "sha256:...",
  "created_at": "2026-05-02T13:42:11Z"
}
```

`created_at` is informative only. MUST NOT influence merge semantics anywhere.

## `lock`

Empty regular file. Exists only to host an `fcntl.flock(LOCK_EX)`. Contents are ignored.

## `tmp/`

Scratch space for atomic writes. Files here have unpredictable names (created via
`tempfile.NamedTemporaryFile(dir=tmp/)` or `mkstemp`). Stragglers from a crash MAY
be removed on the next acquire-lock cycle.

## Agent notes
> Never write any file under the sidecar except via the documented helpers (store_base, write_state, create_conflict_dir). All paths must be derived from the sidecar root, never from user input — see P-path-traversal-safety.
> `state.json` writes themselves go through atomic-replace (write to `tmp/state.json.<rand>`, fsync, rename). A torn `state.json` is `CorruptSidecar`.

## Related files
- `spec/data-model.md` — paths and hashes
- `spec/algorithms.md` — when each file is written
