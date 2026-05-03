---
id: conventions-testing-strategy
type: procedure
summary: Test levels, naming, fixtures, and the no-mocks-on-fs rule.
domain: conventions
last-updated: 2026-05-02
depends-on: [properties-functional, properties-edge-cases]
refines: []
related: [conventions-code-style]
---

# Testing strategy

## One-liner
Tests are real-filesystem, property-IDed, pytest-driven. No mocking of OS primitives — correctness lives in fsync/rename/flock.

## Levels

1. **Unit** — pure modules (`hash`, `paths`, parts of `merge`). Tiny, fast.
2. **Module integration** — `atomic_write`, `lock`, `store` against `tmp_path`.
3. **Command** — `cmd_<name>(args)` end-to-end with real sidecar dirs.
4. **CLI** — invoke `python -m stile <subcommand>` via `subprocess` and parse JSON.
5. **Smoke** — T10 atomicity test: threaded writer + reader hashing FILE.

Aim for 3+ tests per source file (per spec-driven-dev guidance).

## Naming

```
test_<module>.py
def test_<TID>_<PID>_<short_description>():
    ...
```

Examples:
- `test_save.py::test_T3_P12_direct_save`
- `test_save_conflict.py::test_T6_P4_stale_conflicting_save_writes_artifacts`
- `test_T10_atomicity.py::test_T10_P2_concurrent_reader_never_sees_torn_file`

The TID/PID prefix means a property regression is grep-able.

## Fixtures

- Use `tmp_path` (pytest builtin) for any test that touches the filesystem.
- A `managed_file` fixture creates `tmp_path/file.txt`, runs `init`, yields the path.
- A `with_pending_conflict` fixture extends `managed_file` by triggering T6 and yielding `(path, conflict_id)`.

Define these in `tests/conftest.py`.

## Mocking rules

- **DO NOT mock** `os.replace`, `os.fsync`, `fcntl.flock`, `subprocess.run`. Their behaviour is the thing under test.
- **DO mock** time/date if a test cares about `created_at` deterministically (rarely).
- **DO use** `monkeypatch` to drop entries from `PATH` (e.g. T20: simulate missing `diff3`).

## Property-based tests

For hash and merge round-trips, use small randomised inputs:

```python
def test_P5_hash_byte_exactness_random_bytes():
    for _ in range(100):
        b = os.urandom(random.randint(0, 4096))
        assert hash_bytes(b) == "sha256:" + hashlib.sha256(b).hexdigest()
```

No `hypothesis` (would be a third-party runtime test dep — fine, but stdlib `random` is enough for v0).

## Atomicity (T10) test pattern

```python
def test_T10_atomicity():
    # writer thread: alternate two large contents
    # reader thread: read FILE bytes, hash, append to observed list
    # run for ~2s OR 100 cycles
    # assert: every observed hash in {H(V1), H(V2)}; no zero-length read
```

Use `threading.Thread`, not `multiprocessing` (lighter, sufficient for the sidecar lock invariants we test).

## Coverage target

Not a percentage — a checklist. Every property in `properties/functional.md` has at least one test that names it. Every error name in `spec/error-taxonomy.md` has at least one test that triggers it.

## Agent notes
> If a test needs to "assert it didn't write FILE", capture file mtime/contents before and assert byte-equality after.
> If you need a 3-way merge fixture, build it inline in the test from base/current/proposed bytes — don't share across tests, makes failures harder to diagnose.

## Related files
- `../properties/functional.md` — property IDs to use in test names
- `../properties/edge-cases.md` — TIDs to use in test names
- `../runbooks/audit-checklist.md` — coverage audit
