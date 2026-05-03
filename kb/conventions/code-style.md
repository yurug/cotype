---
id: conventions-code-style
type: procedure
summary: Code style — Python conventions, size limits, type hints, documentation rules.
domain: conventions
last-updated: 2026-05-02
depends-on: []
refines: []
related: [conventions-error-handling, conventions-testing-strategy]
---

# Code style

## One-liner
KISS Python: typed, small files/functions, literate comments, stdlib only.

## Hard rules

- **Python 3.11+ syntax**. Use modern features where they help (`match`, `tomllib`, PEP 604 unions).
- **Type hints on every public function**. `from __future__ import annotations` at the top of every module.
- **No third-party runtime imports** (ADR-0001). `pytest` is the only test-time dep.
- **Files < 200 lines.** Split when bigger.
- **Functions < 30 lines.** Extract helpers when bigger.
- **No `print()` outside `cli.py`.** Commands return dicts; the CLI emits.

## Module conventions

Every module starts with:

```python
"""<one-line module purpose>.

Spec refs: <link or section IDs>
Properties enforced: P<N>, P<M> (when relevant)
Key design notes: <bullet of non-obvious decisions>
"""
from __future__ import annotations
```

## Function conventions

Every public function gets a docstring:

```python
def atomic_replace(target: Path, content: bytes, sidecar: Path) -> None:
    """Replace `target` with `content` atomically.

    Steps: write tmp -> fsync tmp -> copymode -> os.replace -> fsync parent.
    Holds: the caller MUST already hold the sidecar flock (see ADR-0003).

    Args:
        target: real path of the managed file.
        content: bytes to write.
        sidecar: sidecar dir; tmp dir is `<sidecar>/tmp`.

    Raises:
        IoError: any OSError during the write/fsync/replace sequence.

    Invariants enforced: P2 (atomic visibility), P12 (atomic replace), P13 (mode preservation).
    """
```

## Comment style

Three kinds, used sparingly:

- **WHAT**: above non-trivial algorithmic steps.
- **WHY**: above conditionals whose rationale is non-obvious from the code.
- **`# inv: P<N>`**: short marker right next to a line that enforces a property.

Skip comments that just restate the code.

## Naming

- `snake_case` for functions, modules, variables.
- `PascalCase` for classes (only `StileError` subclasses in v0).
- Constants: `SCREAMING_SNAKE`. Defined at module top.
- Internal helpers: `_leading_underscore`. Public functions: no prefix.

## Imports

- Group: stdlib, then local (`from stile import ...`). One blank line between.
- No relative imports across packages (`from stile.commands.save import cmd_save`, not `from .save import ...` outside `commands/`).
- `commands/` may use `from .save import cmd_save`-style intra-package imports.

## File-level structure

Order within a module:
1. Module docstring
2. `from __future__ import annotations`
3. Stdlib imports
4. Local imports
5. Constants
6. Types / dataclasses
7. Public functions
8. Private helpers

## Things we DO NOT do

- No metaclasses, no decorators beyond `@contextmanager` and `@dataclass(frozen=True)`.
- No global mutable state. Pass things in, return things out.
- No `try: except Exception:` swallowers. Catch specific exceptions.
- No string-formatted shell commands. `subprocess.run([...])` always.
- No `os.path.*` when `pathlib.Path` does the job.

## Agent notes
> If a function is hard to write under 30 lines, the abstraction is wrong; split it.
> Pure functions (hash, paths) should be 100% deterministic and side-effect-free; they get the heaviest test coverage.

## Related files
- `error-handling.md` — exceptions and exit-code mapping
- `testing-strategy.md` — what counts as a test
- `../architecture/overview.md` — module dependency rules
