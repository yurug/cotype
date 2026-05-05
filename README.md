# cotype

[![PyPI](https://img.shields.io/pypi/v/cotype.svg)](https://pypi.org/project/cotype/)
[![tests](https://github.com/yurug/cotype/actions/workflows/test.yml/badge.svg)](https://github.com/yurug/cotype/actions/workflows/test.yml)
[![License: MIT](https://img.shields.io/badge/License-MIT-blue.svg)](LICENSE)

> **A shared text file as the workspace for you and your AI agents — kept consistent, save by save.**

You write. Your agents write. **In the same file. At the same time.** No transcripts to scroll, no chat windows, no lost edits. Disjoint edits auto-merge. Overlapping edits surface as inline conflicts you settle in your editor. No actor — human, agent, or script — ever silently overwrites another.

![cotype demo: three Claude personas brainstorming with a user in one shared file](examples/demo-crepe/demo.gif)

*Three Claude personas (cook, logistics, ux-designer) plus a note-taker brainstorm a school crêpe stand with the user — all in one `brainstorm.md`. Each persona owns its `## agent:<role>` section. Cotype reconciles every save in the background.*

---

## Why this, instead of a chat?

Chat transcripts drift away from the work. The thing you actually want at the end of the session — the design doc, the spec, the code, the meeting notes — is buried under twenty rounds of "thanks, here's the updated version."

**Flip it.** The file *is* the conversation:

- **You** type your question or instruction under `## user`.
- **Each agent** edits its own `## agent:<name>` section in place to reply.
- **Everyone** sees the latest version in their editor in real time.
- **Concurrent saves** are reconciled by 3-way merge — the same machinery git uses, but tiny, single-file, and protocol-driven.

If you've ever lost an agent's edits to your own save (or vice versa), that's the problem cotype fixes.

---

## Install

```bash
pip install cotype
```

Requires Python ≥ 3.11 and POSIX `diff3` (in `diffutils`, present on every Linux/macOS).

## 30-second tour

```bash
echo "# notes" > task.md
cotype init task.md           # start managing the file

# capture a base, edit, save -- the universal protocol
meta=$(cotype open task.md --json)
base_sha=$(echo "$meta" | jq -r .base_sha)
echo -e "# notes\n\nFirst idea." \
  | cotype save task.md --base-sha "$base_sha" --actor me --json
```

`cotype --help` shows the full protocol — agents that read it can use cotype correctly without further docs.

---

## Run a multi-agent brainstorm

The demo above is one bash script away:

```bash
./examples/headless-agents.sh task.md cook logistics ux-designer note-taker
```

Each agent owns a `## agent:<role>` section and replies terse on every change. By construction, two agents editing two different sections cannot conflict. Copy [`examples/headless-agents.sh`](examples/headless-agents.sh) and tweak the prompt or roles for your use case.

## Editor integration

- **Emacs** — `cotype-mode` minor mode lives in [`editors/emacs/`](editors/emacs/), [submitted to MELPA](https://github.com/melpa/melpa/pull/9998). Routes `C-x C-s` through `cotype save`; reverts buffers automatically when an agent writes; surfaces conflicts inline as diff3 markers in the buffer.
- **Other editors** — the CLI is editor-agnostic; integration is just two CLI calls (`cotype open` on load, `cotype save` on write). PRs welcome.

---

## Documentation

| Where | What |
|---|---|
| `cotype --help` | Self-describing; the on-screen protocol is enough for an agent to operate the tool from a sandbox. |
| [`cli/README.md`](cli/README.md) | **CLI reference**: every command, flag, exit code, error name, and the editor / agent caller protocols. |
| [`kb/`](kb/) | Normative spec, properties, ADRs, and design notes. Optimized for agents reading the repository. |
| [`examples/`](examples/) | Runnable demos — the multi-agent brainstorm pictured above, plus an offline protocol-only walkthrough. |
| [`CHANGELOG.md`](CHANGELOG.md) | Per-release notes. |

## Philosophy

Cotype is intentionally tiny: `open`, `save`, and a 3-way merge when the base is stale. No daemon, no event log, no CRDT, no network sync, no semantic edits, no multi-file transactions. The PRD's [non-goals list](kb/domain/prd.md) is load-bearing — cotype does *one* thing and does it right. Reach for git for project-wide history; reach for cotype when one file is the unit of collaboration.

## License

MIT. See [LICENSE](LICENSE).
