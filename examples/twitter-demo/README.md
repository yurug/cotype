# examples/twitter-demo

A 15-second scripted demo built to advertise `stile` on Twitter/X: one
user (in Emacs) and three agents writing the same `task.md` and the
file staying coherent through it all.

## What the viewer sees

1. The starting `task.md` — a `# Refactor src/auth.py` heading, a
   `## user` question, and three empty agent slots labelled
   `## agent:reviewer`, `## agent:linter`, `## agent:tester`.
2. A single command (`agents`) that, behind the scenes, captures one
   shared base and dispatches three agents that each fill in their own
   slot. The output:
   ```
     agent:reviewer  save: direct
     agent:linter    save: merged
     agent:tester    save: merged
   ```
   The first lands directly; the next two are computed against a now-stale
   base, but their edits are in disjoint regions so `stile` 3-way merges
   them cleanly. *That* is the headline story.
3. The final `task.md` — all four sections present, attributed, and in
   order. No actor's bytes were lost.
4. Caption: `# four writers, no lost edits.`

## Run it live (no recording)

```bash
cd examples/twitter-demo
./demo.sh                 # runs the whole thing in your terminal
```

You should see exactly the output described above. The script is
idempotent: a `/tmp/stile-twitter-demo` working directory is recreated
on every run.

## Render to a GIF/MP4 with VHS

[VHS](https://github.com/charmbracelet/vhs) reads a declarative tape file
and produces a deterministic GIF or MP4 — perfect for social media.

```bash
brew install vhs                 # macOS
# or
nix run nixpkgs#vhs              # nix
# or see https://github.com/charmbracelet/vhs#installation

cd examples/twitter-demo
vhs demo.tape
# -> demo.gif  +  demo.mp4
```

The `.tape` file is one-pane, ~13 seconds, theme = Dracula, 1100×720. To
tweak any of those, edit the `Set` lines at the top.

## Render with asciinema (alternative)

```bash
brew install asciinema agg       # asciinema records, agg converts to GIF

cd examples/twitter-demo
asciinema rec --command='./demo.sh' demo.cast
agg demo.cast demo.gif
```

## Files

| File | What it is |
|---|---|
| `setup.sh` | Recreates `/tmp/stile-twitter-demo/task.md` with the four labelled slots and runs `stile init`. Idempotent. |
| `orchestrate.py` | Captures one base via `stile open`, dispatches three "agents" (each replaces only its own `SLOT_*` placeholder), saves with the same `--base-sha`. Produces `direct, merged, merged`. |
| `demo.sh` | Wires `setup.sh` and `orchestrate.py` into a paced live preview. |
| `demo.tape` | VHS recipe — same flow, deterministic timing, renders to GIF/MP4. |
| `agents/` | Three earlier mock agents (`reviewer.py`, `linter.py`, `tester.py`) used by `agent-loop` for sequential demos. The Twitter demo uses `orchestrate.py` instead because it has to share one base across all three. |

## Why "merged" is the visual hook

`stile save` returns one of `direct`, `merged`, `noop`, or `conflict`. A
demo that only shows `direct` could be confused with `cat >> file`. The
`merged` outcome is what makes the value proposition concrete: the
linter and the tester each captured their base when the file was empty,
both saved against that stale base, and `stile` invoked POSIX `diff3 -m`
to land both their changes — nothing lost, nothing overwritten.

If you want a 30-second longer cut showing a conflict + `stile resolve
--use-merged` recovery flow, fork `orchestrate.py` to have one of the
agents target the same slot as another. The mechanics are identical.
