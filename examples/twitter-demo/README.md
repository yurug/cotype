# examples/twitter-demo

Three scripted demos for advertising `stile`. Pick by the trade-off you
care about most:

| File | Story | Length | Determinism | Cost |
|---|---|---|---|---|
| `demo-claude.sh` / `demo-claude.tape` | **Real Claude agents** + multi-round ping-pong (puppeteer types user follow-ups into Emacs). The richest demo — shows the actual integration end-to-end. | ~50 s | non-deterministic | a few cents per render with Haiku via the `claude` CLI; free if `claude` isn't on PATH (canned bodies) |
| `demo.sh` / `demo.tape` | **Mock agents**, single round, all three save concurrently and produce `direct`, `merged`, `merged` via `diff3 -m`. The protocol-shape demo. | ~13 s | deterministic | none |
| `simple-demo.sh` / `simple-demo.tape` | Single pane, scripted typed transcript. | ~13 s | deterministic | none |

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

## The Claude / multi-round demo (`demo-claude.sh`)

A funny pedagogical scenario: **build a tiny backpack-sized rocket** as
a structured Markdown document. The user owns one section; three agents
each own another and **react to the section they depend on**:

```text
   ┌─────────────┐         ┌──────────────┐
   │  user owns  │ ◀───── reads ──── ┌────┴────┐
   │ ## require- │                   │ engineer│ ──────┬──── reads ────┐
   │   ments     │ ───── reads ───▶  └────┬────┘       │               │
   └─────────────┘                        │            ▼               ▼
                                          │      ┌─────────┐   ┌──────────┐
                                          └────▶ │ tester  │   │ marketer │
                                                 └─────────┘   └──────────┘
                                                  ## tester     ## marketer
                                                  reacts to     reacts to
                                                  ## engineer   ## engineer
```

The seed file:

```markdown
# 🚀 Tiny rocket build

## requirements
- fits in a backpack
- launches at least 50 m

## engineer
(no design yet -- waiting on requirements)

## tester
(no plan yet -- waiting on engineer)

## marketer
(no tagline yet -- waiting on engineer)
```

Each agent **regenerates the BODY of its own section** when its
dependency section changes, by computing the new content (real Claude
via `claude --print -p ...`, or canned per-round bodies in fake mode)
and submitting the entire document to `stile save`. Two key safety
properties fall out of this design:

1. **Concurrent saves to different sections merge cleanly.** Engineer
   editing `## engineer` and marketer editing `## marketer` produce
   *disjoint* diffs against the base. The first save lands `direct`;
   the second one comes back as `merged` (POSIX `diff3 -m`). No coord
   lock required -- the document structure does the work.
2. **Idempotence on no-op cycles.** Each agent tracks the SHA-256 of its
   dependency section; until that hash changes, the agent doesn't write
   anything (would be a `noop` save anyway).

### What the recording shows

```text
T=0      tmux comes up; emacs opens task.md; stile-mode lights up.
T=1-3s   engineer reacts to seeded `## requirements` and saves
         "PVC pipe + B6-4 motor, 30 cm, 200 g."
         tester and marketer were waiting on the engineer placeholder;
         once engineer lands, they cascade: tester writes a drop-test
         plan; marketer writes "POCKET ROCKET — fits where physics
         doesn't."
T=12s    puppeteer M-x's `stile-demo-add-requirement` and types
         "must survive a 5-year-old throwing it at a wall" under
         `## requirements`. Stile-mode saves through `stile save`.
T=13-16s engineer regenerates `## engineer` with an impact-rated foam-
         over-PVC nose cone; tester adds a pendulum wall-impact test;
         marketer rebrands to "Still flying after the kid's tantrum."
T=27s    puppeteer adds "BOM under $5 (no NASA contracts)".
T=28-31s engineer downgrades to cardboard + electrical tape; tester
         drops the wall-impact test (out of budget); marketer goes
         "Less than a burrito. More fun than a kite."
```

If `claude` is not on `PATH` (or `STILE_DEMO_FAKE_CLAUDE=1`), the
agents use canned per-round bodies indexed by `rounds_done`; the
recording is fully deterministic.

### Run live

```bash
cd examples/twitter-demo
./demo-claude.sh
```

Detach with `C-b d`. Kill with `tmux kill-session -t stile-claude-demo`.

### Render

```bash
vhs demo-claude.tape   # produces demo-claude.gif + .mp4
```

## File reference

| File | Role |
|---|---|
| `setup.sh` | Seeds `task.md` with four labelled slots (`SLOT_REVIEWER`, etc.) for `demo.sh`. |
| `setup-claude.sh` | Seeds `task.md` with just the user's question for `demo-claude.sh`. |
| `bg-viewer.sh` | Top-pane plain "live editor" loop — fallback when `emacs` is not on `PATH`. |
| `bg-agent.py` | Mock agent for `demo.sh`. Barrier + slot replacement; one save then idle. |
| `bg-claude.py` | Polling agent for `demo-claude.sh`. Calls `claude` CLI (or canned bodies). Multi-round. |
| `bg-puppeteer.py` | Drives Emacs via `tmux send-keys` to type user follow-ups in `demo-claude.sh`. |
| `demo-init.el` | Emacs init that loads `editors/emacs/stile.el` and auto-enables `stile-mode`. |
| `orchestrate.py` | Sequential dispatcher used by `simple-demo.sh`. |
| `agents/{reviewer,linter,tester}.py` | Single-shot mocks used by the agent-loop example (separate from these demos). |

## Why the cascade is the visual hook

A demo where every save shows `direct` could be confused with `cat >>
file`. The `merged` outcome is what makes `stile` legibly *different*:
two real agents each captured their base when the file was empty, both
saved against that stale base, and `stile` reconciled them via `diff3
-m` with no human in the loop. That is the headline.

If you want a 30s longer cut showing a conflict + `stile resolve
--use-merged` recovery flow, fork `bg-agent.py` to have one agent
target the same slot as another. The mechanics are unchanged.
