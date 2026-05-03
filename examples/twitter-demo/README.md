# examples/twitter-demo

Two scripted demos for advertising `stile` — pick one based on whether
you want **real concurrent processes** in a multi-pane terminal (the
star demo) or a **paced typed transcript** in a single pane (a fallback
when `tmux` isn't available).

| File | Demo type | Renders to | Best for |
|---|---|---|---|
| `demo.sh` / `demo.tape` | **4-pane tmux**, three real concurrent agent processes | `demo.gif`, `demo.mp4` | Twitter/X — shows real `direct`, `merged`, `merged` cascade |
| `simple-demo.sh` / `simple-demo.tape` | Single pane, scripted output | `simple-demo.gif`, `simple-demo.mp4` | Hosts without `tmux`, or as a typed-transcript embed in a blog |

Both share the same setup (`setup.sh`) and helper logic; only the
presentation differs.

## What the multi-pane demo shows

```
+-----------------------------------------------+
|                                               |
|  ─── task.md ─── (your editor)                |
|                                               |
|  # Refactor src/auth.py                       |
|  ## user                                      |
|  What's brittle here?                         |
|  ## agent:reviewer                            |
|  Three concerns:                              |
|    ...                                        |
|  ## agent:linter                              |
|  12 findings (3 must-fix):                    |
|    ...                                        |
|  ## agent:tester                              |
|  Coverage gaps:                               |
|    ...                                        |
|                                               |
+--------------+--------------+-----------------+
| agent:reviewer | agent:linter | agent:tester  |
| ─────────────  | ────────────  | ────────────  |
| · open (base.) | · open (base.) | · open (base.)|
| ✓ save: direct | ⚡ save: merged | ⚡ save: merged|
+--------------+--------------+-----------------+
```

Three real processes each run `stile open` (capturing the same base),
synchronize at a barrier so they all hold an identical `base_sha`,
then save with a small post-barrier jitter. The first save lands
`direct`. The next two see a now-stale base + non-overlapping diffs, so
`stile` invokes POSIX `diff3 -m` and 3-way merges them. The top pane
re-renders on every change, so the viewer sees the file fill in section
by section.

This is the headline value-prop visualised: **multiple writers, no
overwrites, no lost work**.

## Run live (no recording)

Requires `tmux` and `stile` on `PATH`.

```bash
cd examples/twitter-demo
./demo.sh
# Inside tmux: detach with Ctrl-B then d
# Cleanup:  tmux kill-session -t stile-tmux-demo
```

You should see the 4-pane layout. After a brief pause (all three agents
capture and synchronise at the barrier), the bottom panes show the
save cascade and the top pane re-renders to the fully-populated file.

## Render to a GIF/MP4 with VHS

[VHS](https://github.com/charmbracelet/vhs) records terminal sessions
deterministically from a script.

```bash
brew install vhs                  # macOS
nix run nixpkgs#vhs               # nix
# see https://github.com/charmbracelet/vhs#installation for other OSes

cd examples/twitter-demo
vhs demo.tape                     # produces demo.gif + demo.mp4
```

The `.tape` file is ~12 seconds visible, theme = Dracula, 1400×900. Edit
the `Set` lines at the top to tweak.

## Render with asciinema (alternative)

```bash
brew install asciinema agg

cd examples/twitter-demo
asciinema rec --command='./demo.sh' demo.cast
agg demo.cast demo.gif
```

Note: asciinema records the full session including your detach key
sequence; you may want to trim the cast file.

## File reference

| File | Role |
|---|---|
| `setup.sh` | Recreates `/tmp/stile-twitter-demo/task.md` with four labelled slots and runs `stile init`. Idempotent. |
| `bg-viewer.sh` | Top-pane "live editor view" — re-renders `task.md` whenever its content hash changes. |
| `bg-agent.py` | One agent process per bottom pane. Captures base, waits at the barrier, saves after a small jitter. Idles after one save so the result stays on screen. |
| `demo.sh` | Wires the above into the 4-pane tmux layout. |
| `demo.tape` | VHS recipe — runs `demo.sh`, lets the cascade play out, detaches and kills the session at the end. |
| `orchestrate.py` | Single-process implementation used by `simple-demo.sh`: captures one base, dispatches three saves sequentially against it. |
| `agents/{reviewer,linter,tester}.py` | Earlier single-shot mocks reused by the agent-loop example; the multi-pane demo uses `bg-agent.py` instead. |
| `simple-demo.sh` / `simple-demo.tape` | Single-pane narrated alternative. |

## Why the cascade is the visual hook

A demo where every save shows `direct` could be confused with `cat >>
file`. The `merged` outcome is what makes `stile` legibly *different*:
two real agents each captured their base when the file was empty, both
saved against that stale base, and `stile` reconciled them via `diff3
-m` with no human in the loop. That is the headline.

If you want a 30s longer cut showing a conflict + `stile resolve
--use-merged` recovery flow, fork `bg-agent.py` to have one agent
target the same slot as another. The mechanics are unchanged.
