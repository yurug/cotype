# editors/emacs

A minor mode (`cotype-mode`) that routes Emacs saves through the `cotype`
CLI, so a file can be edited concurrently by you, AI agents, and other
processes without lost updates.

This is the canonical Emacs integration in the cotype monorepo. It is
self-contained: the only prerequisite from the rest of the repo is a
working `cotype` on `PATH`, installed from `cli/`.

## Requirements

- Emacs ≥ 27.1 (built-in `json-parse-buffer`)
- `cotype` on `PATH` (`pip install -e cli/` from the monorepo root)
- POSIX `diff3` (from `diffutils`)

## Install

Drop `cotype.el` somewhere on `load-path` and require it:

```elisp
(add-to-list 'load-path "~/path/to/cotype/editors/emacs")
(require 'cotype)

;; Optional: auto-enable cotype-mode in any buffer whose file has
;; a .<basename>.cotype/ sidecar already.
(add-hook 'find-file-hook #'cotype-maybe-enable)
```

Customise:

```elisp
(setq cotype-executable "/usr/local/bin/cotype"   ;; default: "cotype"
      cotype-actor      "emacs:yann")            ;; default: "emacs"
```

## Usage

| Command | What it does |
|---|---|
| `M-x cotype-init` | Run `cotype init` on the buffer's file and enable `cotype-mode`. |
| `M-x cotype-mode` | Toggle the minor mode for this buffer. |
| `M-x cotype-status` | Echo the current `cotype status` of the buffer's file. |
| `M-x cotype-resolve` | After editing out the diff3 conflict markers in the buffer, clear the pending state. |

Once `cotype-mode` is on (lighter: ` cotype`), pressing `C-x C-s` runs
`cotype save --base-sha <captured>` instead of writing the file
directly. You'll see one of:

- `cotype: saved (direct)` — the file was up to date; your bytes landed.
- `cotype: saved (merged)` — another actor edited disjoint regions; the
  3-way merge is on disk and your buffer was reverted to match.
- `cotype: saved (noop)` — the file already matches what you tried to save.
- `cotype: conflict <id> -- edit out markers, then M-x cotype-resolve` —
   FILE has been rewritten with diff3 markers and the buffer reverted
   to show them. Edit out the `<<<<<<<` / `=======` / `>>>>>>>` blocks,
   then run `M-x cotype-resolve` to clear the pending state. (No need
   to save the buffer first — `cotype-resolve` flushes it for you.)

## Manual smoke test

The plugin has no automated test suite (would require Emacs in CI).
Verify it by hand:

```bash
mkdir -p /tmp/cotype-emacs && cd /tmp/cotype-emacs
echo "hello" > note.txt
cotype init note.txt --json

emacs -Q -l ~/path/to/cotype/editors/emacs/cotype.el note.txt
```

In Emacs:

1. `M-x cotype-mode` → modeline shows ` cotype`, the buffer is reloaded
   from the captured base, point stays where it was.
2. Edit, then `C-x C-s` → echo area: `cotype: saved (direct)`.
3. From a separate shell: `printf 'concurrent\n' > note.txt`. Back in
   Emacs, edit again and save → `cotype: saved (merged)` (or `conflict`
   if your edit overlaps).

## How it implements the protocol

The integration mirrors `kb/spec/protocols.md`:

- **On enable**: `cotype open FILE --json` → store `base_sha` buffer-locally;
  reload buffer from `base_path`. Reloading guarantees the buffer matches
  what cotype believes the base is, closing the SPEC's "forbidden protocol"
  race window between Emacs reading the file and our `cotype open` call.
- **On save**: pipe the buffer through `cotype save --base-sha <captured>
  --actor emacs --json`. Returning `t` from a `write-contents-functions`
  hook suppresses Emacs' default write, so the file is only ever modified
  via `cotype`.
- **On conflict**: `cotype save` rewrote FILE with diff3 markers; the
  buffer is reverted so the user sees those markers in place. After the
  user edits them out, `M-x cotype-resolve` writes the buffer to disk
  (bypassing the save hook, which would be rejected with
  `ConflictPending`) and calls `cotype resolve FILE` to clear the
  pending state.

## How concurrent writes appear in your buffer

When another actor (an AI agent, a formatter, a teammate via SSH) writes
the file through `cotype`, Emacs would normally pop "task.md changed on
disk; really edit buffer?" the next time you type. That breaks the
illusion of a shared workspace. Instead, `cotype-mode` enables
`auto-revert-mode` in the same buffer (controllable via the
`cotype-auto-revert` defcustom, default `t`):

- The buffer reloads silently when the file changes on disk.
- Right after each revert, `cotype-mode` re-runs `cotype open` so the
  buffer-local `base_sha` matches the new on-disk state — your next
  save uses the right base.
- If the buffer has unsaved edits, auto-revert won't silently revert; it
  will warn, and you keep your work.

If you've configured auto-revert globally already, `cotype-mode` won't
toggle it off when you leave the mode. Set `cotype-auto-revert` to `nil`
if you want to drive it yourself.

## Known limitations

- No automated tests.
- No transient/keymap UI; conflict resolution is `M-x cotype-resolve`.
- Auto-save (`#filename#` files) writes outside `write-contents-functions`;
  consider `(setq auto-save-default nil)` in cotype-mode buffers if it
  bothers you. Auto-revert is now coordinated automatically (see above).
- Tramp / remote files: untested. The CLI invocation is local-only.
