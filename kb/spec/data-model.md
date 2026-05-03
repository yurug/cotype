---
id: spec-data-model
type: spec
summary: Hash format, path conventions, sidecar layout, and state.json schema.
domain: spec
last-updated: 2026-05-02
depends-on: [glossary]
refines: [prd]
related: [spec-algorithms, spec-config-and-formats, external-posix-fs]
---

# Data model

## One-liner
Defines hashes, paths, sidecar layout, and the state.json schema. Every other spec file builds on this.

## Scope
Formal definitions only. Algorithms live in `spec/algorithms.md`; error names in `spec/error-taxonomy.md`.

## Hash

```
H(b) = "sha256:" ++ lowercase_hex(SHA256(b))
```

- 64 lowercase hex chars after the `sha256:` prefix.
- Operates on **raw bytes as read from disk**. No line-ending normalisation, no Unicode normalisation, no whitespace trimming, no final-newline coercion.
- The `<hex>` part (without the prefix) is what indexes into `bases/`.

## Paths

Let `FILE` be the (real, symlink-resolved) target path.

```
sidecar(FILE) = dirname(FILE) / ("." ++ basename(FILE) ++ ".stile")
```

Example: `notes/todo.txt` → `notes/.todo.txt.stile`.

`FILE` MUST be a regular file. Reject directories, symlinks-as-target (resolve first), device files, FIFOs, sockets — error name `UnsupportedFile`.

## Sidecar layout

```
.FILE.stile/
  lock                   # advisory flock target (may be empty)
  state.json             # current state (see schema below)
  bases/                 # content-addressed: bases/<hex>
  conflicts/             # one subdir per pending or historical conflict
    <id>/
      meta.json
      base
      current
      proposed
      merged             # SHOULD; contains conflict markers when relevant
  tmp/                   # staging for atomic writes; safe to wipe on next command
```

- **Base storage**: `bases/<hex>` where `<hex>` is `H(content)` minus the `sha256:` prefix. Identical bytes deduplicate naturally.
- **`tmp/`** is the ONLY safe place to create temp files for atomic rename — same filesystem as `FILE` (via the sidecar).

## state.json schema

```json
{
  "format_version": 1,
  "target_path": "../file.txt",
  "last_known_sha": "sha256:...",
  "pending_conflict": null
}
```

When a conflict is pending, `pending_conflict` is:

```json
{
  "id": "<conflict-id>",
  "base_sha": "sha256:...",
  "current_sha": "sha256:...",
  "proposed_sha": "sha256:...",
  "path": ".file.txt.stile/conflicts/<id>"
}
```

Notes:
- `target_path` is stored relative to the sidecar dir; informational only. The actual managed path is implicit (sidecar dir → strip `.` and `.stile`).
- `last_known_sha` is **advisory**. Truth is always `H(read(FILE))` at command time.
- `format_version` is reserved for future migrations. v0 always writes `1` and refuses any other value as `CorruptSidecar`.

## conflict meta.json schema

See `spec/config-and-formats.md`.

## Agent notes
> The hash is the byte-exact identity. Any code path that "cleans up" content before hashing is a bug.
> `last_known_sha` is informational. NEVER make an authorisation/safety decision from it; re-read FILE.
> All paths inside the sidecar are constructed from a fixed relative scheme — never from user input — see `properties/functional.md#P-path-traversal-safety`.

## Related files
- `spec/algorithms.md` — uses these structures
- `spec/config-and-formats.md` — JSON schemas in detail
- `external/posix-fs.md` — atomic-rename / fsync constraints affecting layout choices
