---
id: adr-0001
type: decision
summary: ADR-0001 — implement stile in Python 3.11+ using stdlib only; no third-party runtime deps.
domain: architecture
last-updated: 2026-05-02
depends-on: []
refines: []
related: [architecture-overview, adr-0002]
---

# ADR-0001: Python 3.11+, stdlib only

## Context

`stile` is a v0 CLI focused on correctness and KISS. Implementation candidates: Python, Go, Rust, OCaml. We must pick one before building anything.

Hot paths in the tool:
- SHA-256 of file contents (1 KB to ~50 MB)
- File I/O: read, atomic temp+rename, fsync
- Advisory locking (flock)
- Subprocess invocation of `diff3`
- JSON serialisation (a few hundred bytes)
- argparse-style CLI

None of these are CPU-bound at the language level. SHA-256 in Python's `hashlib` is OpenSSL native. Subprocess and syscalls are kernel work. JSON volume is trivial. The only Python tax is interpreter startup (~30–80 ms cold).

## Decision

Implement in **Python 3.11+, standard library only**, with no third-party runtime dependencies.

Test-time dependency: `pytest` (dev only).

## Consequences

Positive:
- Zero build step. `pip install -e .` or even `python -m stile` from a clone.
- All behaviour is auditable in plain Python.
- stdlib provides every primitive we need (`hashlib`, `fcntl.flock`, `os.replace`, `os.fsync`, `tempfile`, `json`, `argparse`, `subprocess`, `uuid`, `shutil`).
- Trivial portability across Linux/macOS.

Negative:
- ~30–80 ms cold startup per `stile` invocation. Acceptable for editor-paced use; could matter if a caller batches thousands of `save`s (out of scope for v0 — see PRD §5).
- Higher memory floor than a Go/Rust binary. Acceptable.
- No Windows support in v0 (POSIX flock semantics differ; out of scope per NF5).

Rejected alternatives:
- **Go / Rust**: faster startup, single binary, but adds a build pipeline and requires cross-compilation discipline. Premature optimisation for v0.
- **OCaml**: type-safe, but build setup and ecosystem friction outweigh KISS for a tool that is mostly side-effects.

## What this means for implementers

- No `pip install <foo>` for runtime. If you reach for a third-party lib, justify it in a follow-up ADR or do without.
- Stdlib-style: prefer `pathlib.Path`, `subprocess.run([...], check=False)`, `json.dumps(..., indent=2)`.
- Keep `import` lists lean to protect NF6 (startup time). No top-level `import multiprocessing` or other heavy modules.

## Reconsider when

A perf measurement on a real workload shows interpreter startup or runtime as the bottleneck for a real user, not a theoretical one. Then the natural rewrite path is Go or Rust.

## Related files
- `../overview.md`
- `0002-diff3-for-merge.md` — relies on subprocess being cheap and reliable
