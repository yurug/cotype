# Changelog

All notable changes to this project will be documented in this file.

The format follows [Keep a Changelog](https://keepachangelog.com/en/1.1.0/),
and the project adheres to [Semantic Versioning](https://semver.org/spec/v2.0.0.html).

## [Unreleased]

### Changed (BREAKING) — inline conflict resolution

The conflict UX now follows the git-merge pattern: instead of leaving FILE
unchanged and asking the user to find and hand-edit the merged file in a
hidden sidecar directory, `stile save` rewrites FILE in place with
`<<<<<<<` / `=======` / `>>>>>>>` diff3 markers, and the user resolves
inline.

- `stile save` on conflict: FILE now contains the diff3 marker output;
  `state.last_known_sha` becomes the hash of that content; the `conflict`
  JSON envelope gains a `markers_sha` field. Forensic dump under
  `<sidecar>/conflicts/<id>/{base,current,proposed,merged}` is unchanged.
- `stile resolve FILE` is the new flow: reads FILE off disk, refuses if
  diff3 markers remain, otherwise snapshots and clears the pending
  conflict. The old `--conflict-id ID < bytes` and `--use-merged` forms
  are removed; `resolve` takes no flags besides `--actor` / `--json`.
- Product invariant I4 loosened: FILE *does* change on conflict (gains
  markers); the protection is now that further saves are blocked with
  `ConflictPending` until the markers are gone and `resolve` runs.
- `examples/headless-agents.sh` idles agents while a conflict is pending
  instead of burning Claude calls on saves that can never succeed.
- `stile.el`: new `M-x stile-resolve` (replaces `stile-resolve-use-merged`).
  On a save's conflict reply, the buffer is reverted so the user sees
  the markers in their own editor.

Migration: callers using the old `--use-merged` or `--conflict-id` forms
must switch to the new flow (edit FILE, then `stile resolve FILE`).

## [0.1.0] — 2026-05-03

First public release. Two coupled releases under one tag-namespace:

- `stile` (Python CLI), tagged **`v0.1.0`**.
- `stile.el` (Emacs minor mode), tagged **`emacs-v0.1.0`**.

### Added — `stile` CLI (Python)

- Six commands: `init`, `open`, `save`, `status`, `resolve`, `cat-base`.
  - `save` returns one of `direct`, `merged`, `noop`, or `conflict`.
  - `resolve` takes either an explicit `--conflict-id ID < bytes` or a
    `--use-merged` shortcut that reads `<sidecar>/conflicts/<id>/merged`
    after the user has hand-edited it (refuses if `<<<<<<<`/`>>>>>>>`
    markers are still present).
- POSIX `diff3 -m` for 3-way merge; missing `diff3` surfaces as
  `MergeToolError` (exit 7), never as a content conflict.
- Atomic file replacement: `tmp` → `fsync` → `rename` → `fsync(parent)`,
  with mode-bit preservation.
- Advisory `flock` on `<sidecar>/lock` serialises every mutating command.
- 10 stable error names, JSON envelope on `--json`, exit codes per
  `kb/spec/error-taxonomy.md`.
- Python ≥ 3.11, stdlib only. No third-party runtime dependencies.
- 89 pytest tests covering SPEC §14 conformance (T1–T10), every named
  property (P1–P15 plus path-traversal), security edges, and a threaded
  atomic-visibility smoke test.
- CI matrix: GitHub Actions, Linux + macOS × Python 3.11/3.12.

### Added — `stile.el` (Emacs)

- `stile-mode` minor mode that routes `C-x C-s` through `stile save`.
- On activation, runs `stile open` and reloads the buffer from the
  returned `base_path` so the buffer matches what stile believes the
  base is (closes the SPEC's "forbidden protocol" race window).
- Auto-revert + buffer-local `after-revert-hook` to refresh the
  captured `base_sha` whenever the file changes on disk (toggleable
  via `stile-auto-revert`, default `t`).
- Interactive commands: `stile-init`, `stile-mode`, `stile-status`,
  `stile-resolve-use-merged`, `stile-maybe-enable`.
- Conflict path: visits `<sidecar>/conflicts/<id>/merged` in another
  window; user edits and runs `M-x stile-resolve-use-merged` from the
  original buffer to apply.

### Documentation

- Full agent-optimised knowledge base under `kb/` (PRD, normative spec,
  data model, algorithms, API contracts, error taxonomy, race-free
  caller protocols, properties P1–P15, conformance edge cases T1–T22,
  three ADRs, external-dependency notes, conventions, audit checklist).
- `README.md` covers the use case, install, full CLI surface, exit codes,
  scope.
- `editors/emacs/README.md` covers install, manual smoke test, and a
  protocol walk-through.
- Two runnable demos under `examples/`: a deterministic offline
  protocol demo (`agent-loop/`) and a multi-pane real-time demo with
  Emacs and three Claude-driven agents (`demo/`).

### Known limitations (deliberate, see `kb/domain/prd.md` §5)

- Regular UTF-8 text files only.
- Local-only (no network sync, no daemon mode).
- POSIX-only (Linux + macOS); Windows support is out of scope.
- No event sourcing, no CRDT, no semantic edits, no multi-file
  transactions.

[Unreleased]: https://github.com/yurug/stile/compare/v0.1.0...HEAD
[0.1.0]:      https://github.com/yurug/stile/releases/tag/v0.1.0
