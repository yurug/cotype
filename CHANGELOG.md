# Changelog

All notable changes to this project will be documented in this file.

The format follows [Keep a Changelog](https://keepachangelog.com/en/1.1.0/),
and the project adheres to [Semantic Versioning](https://semver.org/spec/v2.0.0.html).

## [Unreleased]

## [0.2.2] — 2026-05-05

CLI-only patch release; no Emacs change.

- `cotype --help` gains a **MINIMIZING CONFLICTS** section listing two
  actionable tricks an agent can apply to reduce false-positive
  conflicts: (1) padding region boundaries with 2+ unchanged anchor
  lines so diff3 separates hunks, and (2) splicing structurally in
  the harness (parse → take own region → splice into base_path bytes)
  so concurrent edits to disjoint regions cannot conflict by
  construction. Points at `examples/headless-agents.sh` as the
  reference Markdown recipe.

## [0.2.1] — 2026-05-05

Patch release. No behavioural changes; polish only.

- `cotype --help` is now agent-grade: top-level help shows the canonical
  shell protocol (open → read base_path → save), the four `save`
  outcomes, the JSON envelope contract, and the exit-code table on one
  screen. Per-subcommand `--help` answers *when* to use each command,
  not just argparse syntax. `--base-sha` and `--actor` flags now have
  per-flag help strings. An LLM agent invoked in a sandbox can
  self-discover the protocol from `cotype --help` alone, without
  needing the repo.
- `cotype.el`: forward-declare `cotype-mode` so the file byte-compiles
  with no warnings; add the MELPA-required `Maintainer:` and
  `Assisted-by:` headers; defer the global `advice-add` to first
  `cotype-mode` activation rather than running it at file-load time.

## [0.2.0] — 2026-05-04

Two coupled releases under the v0.2 tag-namespace:

- `cotype` (Python CLI), tagged **`v0.2.0`**.
- `cotype.el` (Emacs minor mode), tagged **`emacs-v0.2.0`**.

### Changed (BREAKING) — renamed from `stile` to `cotype`

The PyPI name `stile` was already taken; the project has been renamed
to **cotype** (short for "co-typing": multiple actors typing into the
same file). This is a name change only; semantics, CLI surface, and
on-disk format are unchanged apart from the sidecar directory:

- Binary: `stile <cmd>` → `cotype <cmd>`.
- Python package: `import stile` → `import cotype`.
- Sidecar directory: `.<basename>.stile/` → `.<basename>.cotype/`.
- Emacs file/mode: `stile.el` / `stile-mode` → `cotype.el` / `cotype-mode`;
  every `stile-*` interactive command renamed to `cotype-*`.
- Repository: `github.com/yurug/stile` → `github.com/yurug/cotype`
  (GitHub redirects the old URL automatically).

Migration for an existing `.<basename>.stile/` sidecar: rename it to
`.<basename>.cotype/`. Or if you prefer a clean start, delete the old
sidecar and run `cotype init FILE` again — the file content itself is
untouched.

### Changed (BREAKING) — inline conflict resolution

The conflict UX now follows the git-merge pattern: instead of leaving FILE
unchanged and asking the user to find and hand-edit the merged file in a
hidden sidecar directory, `cotype save` rewrites FILE in place with
`<<<<<<<` / `=======` / `>>>>>>>` diff3 markers, and the user resolves
inline.

- `cotype save` on conflict: FILE now contains the diff3 marker output;
  `state.last_known_sha` becomes the hash of that content; the `conflict`
  JSON envelope gains a `markers_sha` field. Forensic dump under
  `<sidecar>/conflicts/<id>/{base,current,proposed,merged}` is unchanged.
- `cotype resolve FILE` is the new flow: reads FILE off disk, refuses if
  diff3 markers remain, otherwise snapshots and clears the pending
  conflict. The old `--conflict-id ID < bytes` and `--use-merged` forms
  are removed; `resolve` takes no flags besides `--actor` / `--json`.
- `ConflictIdMismatch` error class removed (no caller-supplied id any
  longer; conflict ids are uuid4-hex generated server-side and never
  composed from CLI input).
- Product invariant I4 loosened: FILE *does* change on conflict (gains
  markers); the protection is now that further saves are blocked with
  `ConflictPending` until the markers are gone and `resolve` runs.

Migration: callers using the old `--use-merged` or `--conflict-id` forms
must switch to the new flow (edit FILE, then `cotype resolve FILE`).

### Added — `cotype.el`

- `M-x cotype-resolve` (replaces `cotype-resolve-use-merged`). On a save's
  conflict reply, the buffer is reverted to show the markers in place;
  after the user edits them out, `cotype-resolve` flushes the buffer to
  disk and clears the pending conflict.
- Suppression of Emacs's modtime prompts inside cotype-mode buffers:
  `ask-user-about-supersession-threat` ("FILE has changed since visited;
  really edit?") and `basic-save-buffer`'s ("Save anyway?") are both
  silenced by refreshing visited-file-modtime — cotype already
  coordinates concurrent saves, so the safety nets are pure friction.
- `cotype--ensure-auto-revert` re-arms `auto-revert-mode` after every
  programmatic revert; Emacs's `preserve-modes` only protects the major
  mode plus a hand-coded list of minors, so without this auto-revert
  was silently dropped on every conflict-induced revert.

### Added — `examples/headless-agents.sh`

A new robust headless harness (referenced from `README.md`) that spawns
N Claude agents on a cotype-managed file:

- Section-aware splice: parses Claude's full-file output, extracts only
  the agent's own `## agent:<role>` body, and splices it into the bytes
  read from `base_path`. By construction, two agents editing two
  different sections cannot produce a 3-way conflict.
- Pre-allocated section template (with per-role placeholder anchors)
  on first run; idles all agents on a pending conflict.
- Configurable model + stagger: `CLAUDE_MODEL` (default
  `claude-sonnet-4-6`) and `STAGGER` (default 3 s) for demo-friendly
  pacing.
- Skip-on-no-change guard kills the "noop save with whitespace drift"
  race that shows up when Claude returns a near-byte-identical copy.

### Added — `examples/demo-crepe/`

A new VHS-recordable brainstorming demo: three personas (cook,
logistics, ux-designer) plus a note-taker collaborate with a simulated
user on a cotype-managed `brainstorm.md` to design a school crêpe stand
serving 300 in 2 hours. Three-pane tmux layout (Emacs viewer up top,
puppeteer + agents log at the bottom), three rounds of user input, then
agents idle on the close.

## [0.1.0] — 2026-05-03

First public release. Two coupled releases under one tag-namespace:

- `cotype` (Python CLI), tagged **`v0.1.0`**.
- `cotype.el` (Emacs minor mode), tagged **`emacs-v0.1.0`**.

### Added — `cotype` CLI (Python)

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

### Added — `cotype.el` (Emacs)

- `cotype-mode` minor mode that routes `C-x C-s` through `cotype save`.
- On activation, runs `cotype open` and reloads the buffer from the
  returned `base_path` so the buffer matches what cotype believes the
  base is (closes the SPEC's "forbidden protocol" race window).
- Auto-revert + buffer-local `after-revert-hook` to refresh the
  captured `base_sha` whenever the file changes on disk (toggleable
  via `cotype-auto-revert`, default `t`).
- Interactive commands: `cotype-init`, `cotype-mode`, `cotype-status`,
  `cotype-resolve-use-merged`, `cotype-maybe-enable`.
- Conflict path: visits `<sidecar>/conflicts/<id>/merged` in another
  window; user edits and runs `M-x cotype-resolve-use-merged` from the
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

[Unreleased]: https://github.com/yurug/cotype/compare/v0.2.2...HEAD
[0.2.2]:      https://github.com/yurug/cotype/releases/tag/v0.2.2
[0.2.1]:      https://github.com/yurug/cotype/releases/tag/v0.2.1
[0.2.0]:      https://github.com/yurug/cotype/releases/tag/v0.2.0
[0.1.0]:      https://github.com/yurug/cotype/releases/tag/v0.1.0
