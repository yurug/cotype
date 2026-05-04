# editors/emacs

A minor mode (`stile-mode`) that routes Emacs saves through the `stile`
CLI, so a file can be edited concurrently by you, AI agents, and other
processes without lost updates.

This is the canonical Emacs integration in the stile monorepo. It is
self-contained: the only prerequisite from the rest of the repo is a
working `stile` on `PATH`, installed from `cli/`.

## Requirements

- Emacs ≥ 27.1 (built-in `json-parse-buffer`)
- `stile` on `PATH` (`pip install -e cli/` from the monorepo root)
- POSIX `diff3` (from `diffutils`)

## Install

Drop `stile.el` somewhere on `load-path` and require it:

```elisp
(add-to-list 'load-path "~/path/to/stile/editors/emacs")
(require 'stile)

;; Optional: auto-enable stile-mode in any buffer whose file has
;; a .<basename>.stile/ sidecar already.
(add-hook 'find-file-hook #'stile-maybe-enable)
```

Customise:

```elisp
(setq stile-executable "/usr/local/bin/stile"   ;; default: "stile"
      stile-actor      "emacs:yann")            ;; default: "emacs"
```

## Usage

| Command | What it does |
|---|---|
| `M-x stile-init` | Run `stile init` on the buffer's file and enable `stile-mode`. |
| `M-x stile-mode` | Toggle the minor mode for this buffer. |
| `M-x stile-status` | Echo the current `stile status` of the buffer's file. |
| `M-x stile-resolve-use-merged` | After editing the merged conflict file, accept it as the resolution. |

Once `stile-mode` is on (lighter: ` stile`), pressing `C-x C-s` runs
`stile save --base-sha <captured>` instead of writing the file
directly. You'll see one of:

- `stile: saved (direct)` — the file was up to date; your bytes landed.
- `stile: saved (merged)` — another actor edited disjoint regions; the
  3-way merge is on disk and your buffer was reverted to match.
- `stile: saved (noop)` — the file already matches what you tried to save.
- `stile: conflict <id> -- edit <merged>, then M-x stile-resolve-use-merged`
   — Emacs opens the merged file in another window. Edit out the
   `<<<<<<<`/`=======`/`>>>>>>>` markers, save that buffer the normal
   way, switch back to the original buffer, and run
   `M-x stile-resolve-use-merged`.

## Manual smoke test

The plugin has no automated test suite (would require Emacs in CI).
Verify it by hand:

```bash
mkdir -p /tmp/stile-emacs && cd /tmp/stile-emacs
echo "hello" > note.txt
stile init note.txt --json

emacs -Q -l ~/path/to/stile/editors/emacs/stile.el note.txt
```

In Emacs:

1. `M-x stile-mode` → modeline shows ` stile`, the buffer is reloaded
   from the captured base, point stays where it was.
2. Edit, then `C-x C-s` → echo area: `stile: saved (direct)`.
3. From a separate shell: `printf 'concurrent\n' > note.txt`. Back in
   Emacs, edit again and save → `stile: saved (merged)` (or `conflict`
   if your edit overlaps).

## How it implements the protocol

The integration mirrors `kb/spec/protocols.md`:

- **On enable**: `stile open FILE --json` → store `base_sha` buffer-locally;
  reload buffer from `base_path`. Reloading guarantees the buffer matches
  what stile believes the base is, closing the SPEC's "forbidden protocol"
  race window between Emacs reading the file and our `stile open` call.
- **On save**: pipe the buffer through `stile save --base-sha <captured>
  --actor emacs --json`. Returning `t` from a `write-contents-functions`
  hook suppresses Emacs' default write, so the file is only ever modified
  via `stile`.
- **On conflict**: visit the conflict's merged file in another window;
  the user resolves manually and then runs `stile-resolve-use-merged`,
  which calls `stile resolve --use-merged` and reverts the original
  buffer.

## How concurrent writes appear in your buffer

When another actor (an AI agent, a formatter, a teammate via SSH) writes
the file through `stile`, Emacs would normally pop "task.md changed on
disk; really edit buffer?" the next time you type. That breaks the
illusion of a shared workspace. Instead, `stile-mode` enables
`auto-revert-mode` in the same buffer (controllable via the
`stile-auto-revert` defcustom, default `t`):

- The buffer reloads silently when the file changes on disk.
- Right after each revert, `stile-mode` re-runs `stile open` so the
  buffer-local `base_sha` matches the new on-disk state — your next
  save uses the right base.
- If the buffer has unsaved edits, auto-revert won't silently revert; it
  will warn, and you keep your work.

If you've configured auto-revert globally already, `stile-mode` won't
toggle it off when you leave the mode. Set `stile-auto-revert` to `nil`
if you want to drive it yourself.

## Known limitations

- No automated tests.
- No transient/keymap UI; conflict resolution is `M-x stile-resolve-use-merged`.
- Auto-save (`#filename#` files) writes outside `write-contents-functions`;
  consider `(setq auto-save-default nil)` in stile-mode buffers if it
  bothers you. Auto-revert is now coordinated automatically (see above).
- Tramp / remote files: untested. The CLI invocation is local-only.
