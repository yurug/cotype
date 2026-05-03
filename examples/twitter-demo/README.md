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

The top pane is a **real Emacs** running our `stile-mode` (the same
integration shipped at `editors/emacs/`). The three bottom panes are
**real processes** running `stile open` and `stile save` against the
same `task.md`. As they save, Emacs's auto-revert reloads the buffer
and the user sees the file grow section by section.

```
+-----------------------------------------------+
|                                               |
|   GNU Emacs (-Q + demo-init.el; stile-mode)   |
|                                               |
|   # Refactor src/auth.py                      |
|   ## user                                     |
|   What's brittle here?                        |
|   ## agent:reviewer                           |
|     Three concerns: ...                       |
|   ## agent:linter                             |
|     12 findings (3 must-fix): ...             |
|   ## agent:tester                             |
|     Coverage gaps: ...                        |
|   --- mode-line --- All L1 (Markdown stile)   |
+--------------+--------------+-----------------+
| agent:reviewer | agent:linter | agent:tester  |
| ─────────────  | ────────────  | ────────────  |
| · open (base.) | · open (base.) | · open (base.)|
| ✓ save: direct | ⚡ save: merged | ⚡ save: merged|
+--------------+--------------+-----------------+
```

Sequence:

1. The four panes appear. Agents print their headers and then sleep a
   short `START_DELAY` (default 2 s) so Emacs has time to start up.
2. Emacs finishes loading: `-Q -l demo-init.el task.md`. The init
   loads `editors/emacs/stile.el` and adds `stile-maybe-enable` to
   `find-file-hook`, so opening `task.md` (which has a sidecar from
   `setup.sh`) immediately enables `stile-mode` in the buffer.
3. The three agent processes wake up, each call `stile open` and
   capture the same `base_sha`, then synchronise at a barrier so they
   all hold an identical view.
4. Post-barrier jitter (0.0 / 0.4 / 0.8 s) cascades the saves: reviewer
   wins `direct`; linter and tester see the now-stale base + disjoint
   diffs and `stile` invokes `diff3 -m` to merge them.
5. After each save, the file's mtime changes; Emacs's auto-revert (via
   file-notify) reloads the buffer; `stile-mode`'s `after-revert-hook`
   re-captures the current base. The user sees the section appear
   *inside* Emacs.

This is the headline value-prop made visible end-to-end: **multiple
writers, no overwrites, no lost work — and the user's editor stays
coherent the whole time**.

## Requirements

| What | Why |
|---|---|
| `tmux` | 4-pane layout |
| `stile` on `PATH` | the actual save protocol (install via `pip install -e cli/`) |
| POSIX `diff3` | 3-way merge engine |
| `emacs` (≥ 27.1) | top-pane viewer; auto-revert + stile-mode |

If `emacs` is absent, `demo.sh` falls back to `bg-viewer.sh` (a plain
`cat` loop) so the demo still runs — but the recording is much less
compelling without the real editor in frame.

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
