# examples/agent-loop

A minimum-viable demo of the headline scenario from `kb/domain/prd.md` US0:
a user and one or more agents collaborate on a single text file via `stile`.
Runs offline with a deterministic mock agent — no LLM required to see the
shape.

## Files

- `agent_mock.py` — a deterministic mock agent. Reads stdin, counts
  `## user` and `## agent` headings, appends a reply if there's a new user
  block, otherwise echoes stdin unchanged.
- `run_agent.py` — single-shot driver. Calls `stile open`, pipes the base
  bytes into the agent, calls `stile save`. Exit code mirrors `stile save`
  (0 saved, 1 conflict).

## Try it offline (no LLM)

From an environment with `stile` on `PATH`:

```bash
mkdir -p /tmp/stile-demo && cd /tmp/stile-demo
cat > task.md <<'EOF'
# Refactor the auth module

## user
Look at src/auth.py and tell me what's brittle.
EOF

python3 path/to/stile/examples/agent-loop/run_agent.py task.md
cat task.md
```

You should now see a `## agent (mock #1)` block appended. Re-run the
driver — `mode: noop`, file unchanged. Add a second `## user` block and
re-run — `mode: direct`, a `## agent (mock #2)` appears.

## Wrap to poll

The driver is single-shot on purpose; polling is one line of shell:

```bash
while true; do
    python3 run_agent.py task.md || break
    sleep 30
done
```

Real agents typically don't poll — they're triggered by file watchers,
git hooks, or explicit user action. But polling is the simplest pattern
and is enough to demonstrate concurrent edits.

## Wire a real LLM

The agent contract is intentionally tiny:

```text
your_agent < base_bytes  > proposed_bytes
```

Provide your own script that takes the file's current bytes on stdin and
prints the proposed new file on stdout. Then:

```bash
python3 run_agent.py task.md --agent ./your_agent.sh --actor agent:reviewer
```

Practical advice for prompt design (mirrors what `agent_mock.py` does
deterministically):

- Tell the model "you are editing this Markdown file in place. Do not
  rewrite sections that aren't yours. Append your output under a
  `## agent (...)` heading."
- Pick a stable convention for which sections each side owns (e.g.
  `## user` for the human, `## agent (<role>)` for agents). Disjoint
  sections auto-merge; overlapping ones conflict.
- Track which user inputs have been answered (the mock does it by
  counting headings; a real agent might use checkboxes or task ids).

## Force a conflict

Show the safety story end-to-end. In one terminal, simulate the user:

```bash
sed -i 's/brittle/fragile/' task.md
```

In another, run the agent against the now-stale base:

```bash
python3 run_agent.py task.md
```

If both edits land on the same line, the driver exits with code 1 and
prints a `conflict_path`. Inspect it:

```bash
ls .task.md.stile/conflicts/<id>/
cat .task.md.stile/conflicts/<id>/merged   # has <<<<<<< / ======= / >>>>>>> markers
```

Edit the merged file, then resolve:

```bash
stile resolve task.md --conflict-id <id> < .task.md.stile/conflicts/<id>/merged
```

After that, `run_agent.py` succeeds again.
