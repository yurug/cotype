---
id: external-diff3
type: external
summary: Runtime behaviour of GNU/POSIX `diff3 -m` — exit codes, output format, edge cases.
domain: external
last-updated: 2026-05-03
depends-on: []
refines: []
related: [adr-0002, spec-algorithms]
---

# External: `diff3 -m`

## One-liner
GNU/POSIX `diff3` does line-based 3-way merge. We invoke it via subprocess. Document its actual runtime behaviour so we don't get surprised.

## Source

`diffutils` (GNU). POSIX-mandated. Found on every Linux/macOS host.

## Invocation

```
diff3 -m MYFILE OLDFILE YOURFILE
```

Where:
- `MYFILE` = the side whose changes are favoured in marker output (`<<<<<<< MYFILE`).
- `OLDFILE` = common ancestor.
- `YOURFILE` = the other side.

For `stile`:
- MYFILE   = `proposed`  (the actor's submission)
- OLDFILE  = `base`      (the snapshot the actor started from)
- YOURFILE = `current`   (what is on disk now)

This matches SPEC §8: `diff3 proposed base current`.

## Exit codes (GNU and POSIX agree)

| Exit | Meaning                                          | stile interpretation |
|------|--------------------------------------------------|----------------------|
| 0    | Clean merge, no overlap                          | `Clean(stdout)`      |
| 1    | Overlap; output contains conflict markers        | `Conflict(stdout)`   |
| 2    | Trouble (file missing, internal error, etc.)    | `MergeToolError`     |

## Output format

- Without `-m`: a sequence of edit instructions; useless to us.
- With `-m`: the merged file content goes to stdout, with conflict markers when needed.

Conflict markers (when exit 1):
```
<<<<<<< MYFILE
proposed lines
||||||| OLDFILE
base lines
=======
current lines
>>>>>>> YOURFILE
```

`stile` writes this verbatim to `conflicts/<id>/merged`.

## Request budget

Per `save`: at most one `diff3` invocation (when stale-base AND not noop). Direct/noop saves do NOT spawn `diff3`. So the budget is **0 or 1 subprocess per `save`**.

Cost: ~5–20 ms wall-time including fork/exec for typical small files.

## Runtime gotchas

- **Argument order is easy to get wrong.** Re-test if you ever swap them.
- **`diff3` reads from files, not stdin.** We MUST write the three blobs to temp files inside `<sidecar>/tmp/`.
- **Trailing-newline handling**: `diff3` may emit a "warning: ... no newline at end of file" on stderr. Treat this as informational; do not classify it as `MergeToolError`. Look at exit code only.
- **Locale**: output of `diff3` is byte-pass-through for content; markers are ASCII. Locale settings do not corrupt content.
- **Encoding**: `diff3` is byte-oriented. UTF-8 sequences pass through unchanged.

### Adjacency

`diff3` merges by hunks: it groups *contiguous* changed lines into one region, and reports a region as conflicting iff both sides modified it. **Adjacent edits — i.e. on neighbouring lines with no unchanged line between them — fall in the same region and are reported as a conflict** even when the bytes don't literally overlap.

Concretely:
```
base:     x\ny\nz\n
current:  x\ny1\nz\n      # edits line 2
proposed: x\ny\nz1\n      # edits line 3
```
diff3 emits a conflict (exit 1). Insert one unchanged line between the two edits and they become independent regions:
```
base:     a\nb\nc\nd\ne\n
current:  a\nB\nc\nd\ne\n   # line 2
proposed: a\nb\nc\nd\nE\n   # line 5
```
diff3 emits a clean merge (exit 0).

This matches SPEC §8's wording (Clean is **SHOULD** for non-overlapping edits, not MUST). `stile` accepts diff3's conservative grouping; we do not try to be smarter.

## Failure modes

- `diff3` not on `PATH` → `FileNotFoundError` from `subprocess.run`. Map to `MergeToolError`.
- `diff3` exits 2 → `MergeToolError` with stderr in the message.
- `diff3` somehow exits with another code (>=2 or negative on signal) → `MergeToolError`.

## Verification

```
$ printf 'x\ny\nz\n' > /tmp/base
$ printf 'x\ny1\nz\n' > /tmp/cur
$ printf 'x\ny\nz1\n' > /tmp/prop
$ diff3 -m /tmp/prop /tmp/base /tmp/cur
x
y1
z1
$ echo $?
0
```

Conflict example:
```
$ printf 'x\ny-current\nz\n' > /tmp/cur
$ printf 'x\ny-proposed\nz\n' > /tmp/prop
$ diff3 -m /tmp/prop /tmp/base /tmp/cur ; echo $?
x
<<<<<<< /tmp/prop
y-proposed
||||||| /tmp/base
y
=======
y-current
>>>>>>> /tmp/cur
z
1
```

## Agent notes
> NEVER invoke via `shell=True`. Always pass args as a list.
> Capture stdout AND stderr. Stdout is content; stderr is diagnostic.
> If a future feature needs structured conflict regions, parse the markers — but dump-as-bytes is enough.

## Related files
- `../architecture/decisions/0002-diff3-for-merge.md`
- `../spec/algorithms.md#merge3-internal`
- `posix-fs.md` — temp-file conventions
