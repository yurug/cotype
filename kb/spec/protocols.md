---
id: spec-protocols
type: spec
summary: Race-free caller protocols -- the exact open/save sequences a correct caller MUST follow.
domain: spec
last-updated: 2026-05-03
depends-on: [spec-algorithms, spec-api-contracts]
refines: []
related: [properties-functional]
---

# Caller protocols

## One-liner
Normative call sequences for editors and processes that want race-free behaviour. Plus the common forbidden pattern that loses updates.

## Scope
What the *caller* must do. The behaviour of `stile` itself is in `algorithms.md`. Any caller that follows these protocols inherits the guarantees in `../properties/functional.md` (P1, P4, P15 in particular).

## Editor protocol

A race-free editor integration MUST use this sequence:

```text
OPEN:
  response = stile open FILE --json
  buffer   = read(response.base_path)
  base_sha = response.base_sha

SAVE:
  response = stile save FILE --base-sha base_sha --actor editor < buffer
  if response.status == "saved":
      base_sha = response.sha
      optionally reload buffer from FILE
  if response.status == "conflict":
      present response.conflict_path to the user
      keep buffer dirty or enter conflict workflow
```

The editor MUST NOT write `FILE` directly while it is under `stile` management.

The reason for loading the buffer from `response.base_path` (and not by re-reading `FILE`) is P15: `base_path` is guaranteed to hash to `base_sha`. Re-reading `FILE` could pick up bytes a concurrent writer just landed -- the editor would then submit `save` with a `base_sha` that does not match the buffer it actually started from.

## Process protocol

A race-free process integration MUST use this sequence:

```text
response  = stile open FILE --json
input     = read(response.base_path)
output    = compute(input)
stile save FILE --base-sha response.base_sha --actor process < output
```

The process MUST NOT write `FILE` directly. There is no privileged "I'm a process" code path -- the editor protocol and the process protocol are the same protocol with a different `--actor` label (see P9, protocol parity).

## Forbidden protocol

This sequence is **not** race-free and silently risks losing updates:

```text
read FILE directly        # bytes A observed
... time passes, another actor may have written FILE ...
stile open FILE           # captures bytes B (possibly != A) as base
edit the bytes you read   # producing C, derived from A, not from B
stile save FILE --base-sha B --actor X < C
```

`stile` cannot detect this misuse. The caller asserts via `--base-sha B` that it edited from B, but it actually edited from A. If A != B, the resulting save violates the spirit of P1 even though the byte-level checks pass.

The fix is to always start from `base_path`. Never from a freelance read of `FILE`.

## Agent notes
> The `base_path` rule is the single most important property for race-free integrations -- everything else is a consequence.
> The forbidden pattern is easy to fall into in shell pipelines (`cat FILE | edit | stile save ...`). Always pipe from `base_path`, not from `FILE`, when going through `stile`.

## Related files
- `algorithms.md` -- what `stile` actually does on each call
- `api-contracts.md` -- the JSON shapes returned to the caller
- `../properties/functional.md` -- P1, P9, P15 referenced above
