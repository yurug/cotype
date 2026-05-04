# Changelog

All notable changes to this project will be documented in this file.

The format follows [Keep a Changelog](https://keepachangelog.com/en/1.1.0/),
and the project adheres to [Semantic Versioning](https://semver.org/spec/v2.0.0.html).

## [Unreleased]

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
