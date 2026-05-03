---
id: conventions-error-handling
type: procedure
summary: How to raise, propagate, and translate errors — exceptions to JSON envelope to exit code.
domain: conventions
last-updated: 2026-05-02
depends-on: [spec-error-taxonomy]
refines: []
related: [conventions-code-style, architecture-overview]
---

# Error handling

## One-liner
Raise typed `StileError` subclasses at the lowest layer that knows the cause; the CLI translates to JSON envelope + exit code.

## The hierarchy lives in `errors.py`

```python
class StileError(Exception):
    name: ClassVar[str] = "StileError"
    exit_code: ClassVar[int] = 6  # default: IO

class UsageError(StileError):       name = "UsageError";       exit_code = 2
class UnsupportedFile(StileError):  name = "UnsupportedFile";  exit_code = 3
class UnmanagedFile(StileError):    name = "UnmanagedFile";    exit_code = 3
class CorruptSidecar(StileError):   name = "CorruptSidecar";   exit_code = 3
class UnknownBase(StileError):      name = "UnknownBase";      exit_code = 4
class ConflictPending(StileError):  name = "ConflictPending";  exit_code = 5
class ConflictIdMismatch(StileError): name = "ConflictIdMismatch"; exit_code = 2
class IoError(StileError):          name = "IoError";          exit_code = 6
class MergeToolError(StileError):   name = "MergeToolError";   exit_code = 7
class InvalidUtf8(StileError):      name = "InvalidUtf8";      exit_code = 3
```

## Raising

- Raise the specific subclass at the lowest layer that has both the name AND a useful message.
- Pass a plain string message; it goes verbatim into the JSON `message` field.

```python
if not bases_path.exists():
    raise UnknownBase(f"base snapshot {hash_str} is not present")
```

## Propagation

- Do NOT translate `StileError` between layers. Let it bubble to the CLI.
- Translate stdlib exceptions at the boundary that creates them:
  ```python
  try:
      content = file_path.read_bytes()
  except OSError as e:
      raise IoError(f"reading {file_path}: {e}") from e
  ```
- Translate `UnicodeDecodeError` to `InvalidUtf8`.
- Translate `subprocess.CalledProcessError` (when bypassing our merge wrapper) and `FileNotFoundError` for `diff3` to `MergeToolError`.

## CLI layer translates everything

```python
try:
    result = cmd_save(args)
    emit_success(result, json=args.json)
    return 0
except StileError as e:
    emit_error(e, json=args.json)
    return e.exit_code
except OSError as e:
    emit_error(IoError(str(e)), json=args.json)
    return 6
```

`emit_error`:

```python
def emit_error(e: StileError, *, json: bool) -> None:
    if json:
        sys.stdout.write(json_module.dumps(
            {"status": "error", "error": e.name, "message": str(e)}, indent=2) + "\n")
    else:
        sys.stderr.write(f"error: {e.name}: {e}\n")
```

## What NEVER happens

- No `except Exception: pass`. Anywhere.
- No silent fallback for `MergeToolError`. We do not reinterpret a missing `diff3` as a content conflict (P10).
- No new error names invented at runtime. The set in `errors.py` is closed; if you need a new one, add it to `spec/error-taxonomy.md` and the test suite first.

## Agent notes
> The exit code lives on the exception class; never hardcode it at the call site.
> If a stdlib exception happens to leak through to the user, that's a bug — wrap it at the boundary.
> `from e` (chain) is good practice but the chain MUST NOT change the user-visible JSON envelope.

## Related files
- `../spec/error-taxonomy.md` — names, codes, triggers
- `../architecture/overview.md` — error hierarchy diagram
- `code-style.md` — broader style rules
