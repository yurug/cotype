# editors/vim — cotype for vim & neovim

A small plugin that routes saves of a cotype-managed file through
`cotype save`, so the file can be edited concurrently by you, AI agents,
and other processes without lost updates.

Works in both **vim** (≥ 8.0) and **neovim** (≥ 0.5). Pure vimscript;
no Lua required, no compiled extensions.

## Requirements

- vim ≥ 8.0 (needs `timer_start` for the auto-revert poll) or neovim ≥ 0.5
- `cotype` on `PATH` (`pip install cotype`)
- POSIX `diff3` (from `diffutils`)

## Install

This plugin lives at `editors/vim/` inside the
[cotype](https://github.com/yurug/cotype) monorepo.

### vim-plug

```vim
Plug 'yurug/cotype', { 'rtp': 'editors/vim' }
```

### lazy.nvim (neovim)

```lua
{
  'yurug/cotype',
  config = function()
    -- After lazy clones the repo, append the plugin's runtimepath.
    local root = vim.fn.stdpath('data') .. '/lazy/cotype/editors/vim'
    vim.opt.runtimepath:append(root)
    vim.cmd('runtime! plugin/cotype.vim')
  end,
}
```

### packer

```lua
use {
  'yurug/cotype',
  rtp = 'editors/vim',
}
```

### Manual

Symlink or copy `editors/vim/plugin/cotype.vim` into a directory on your
`runtimepath`:

```bash
mkdir -p ~/.vim/plugin
cp editors/vim/plugin/cotype.vim ~/.vim/plugin/
# Or for neovim:
mkdir -p ~/.config/nvim/plugin
cp editors/vim/plugin/cotype.vim ~/.config/nvim/plugin/
```

## Usage

Open any cotype-managed file (one with a `.<basename>.cotype/` sidecar);
the plugin auto-enables. To start managing a fresh file, run
`:CotypeInit`.

| Command          | What it does |
|------------------|---|
| `:CotypeInit`    | `cotype init` on the buffer's file and enable the mode. |
| `:CotypeMode`    | Toggle the mode for this buffer. |
| `:CotypeEnable`  | Enable the mode without re-running `init`. |
| `:CotypeDisable` | Stop intercepting saves on this buffer. |
| `:CotypeStatus`  | Echo the current cotype state. |
| `:CotypeResolve` | After editing out diff3 markers, clear the pending conflict. |

`:w` (and any save) routes through `cotype save` and produces one of:

- `cotype: saved (direct)` — the file was up to date; your bytes landed.
- `cotype: saved (merged)` — another actor edited disjoint regions; the
  3-way merge is on disk and your buffer was reloaded to match.
- `cotype: saved (noop)` — the file already matches what you tried to save.
- `cotype: conflict <id> -- edit out markers, then :CotypeResolve` — the
  file has been rewritten with `<<<<<<<` / `=======` / `>>>>>>>` markers
  and the buffer reloaded to show them. Edit them out and run
  `:CotypeResolve`.

## Options

Set these *before* the plugin loads (e.g. in your `vimrc` / `init.lua`):

| Variable                          | Default     | What it does |
|-----------------------------------|-------------|---|
| `g:cotype_executable`             | `'cotype'`  | Path to the cotype CLI. |
| `g:cotype_actor`                  | `'vim'`     | Default `--actor` label sent on save. |
| `g:cotype_auto_enable`            | `1`         | If `1`, auto-enable on `BufReadPost` for files with a sidecar. |
| `g:cotype_auto_revert`            | `1`         | If `1`, set `'autoread'` and poll `:checktime` on `CursorHold`. |
| `g:cotype_auto_revert_interval`   | `1000`      | `'updatetime'` ceiling in ms — smaller = faster auto-revert detection. |

## Concurrent writes

With `g:cotype_auto_revert = 1` (the default), the plugin starts a
buffer-local repeating timer (`timer_start`) that runs `:checktime`
every `g:cotype_auto_revert_interval` ms (1 s by default), regardless
of cursor activity. Combined with `'autoread'`, external writes via
cotype show up in your buffer within ~1 s — even if your hands are off
the keyboard.

If your buffer is **modified** when an external write lands, vim still
warns *"WARNING: The file has been changed since reading it!!!"* —
cotype resolves whatever happens semantically through its 3-way merge
on the next save, but the warning prompt itself isn't suppressed by
this plugin. (The Emacs companion does suppress an analogous warning;
PRs to do the same in vim are welcome.)

## How it implements the protocol

The integration mirrors [`kb/spec/protocols.md`](../../kb/spec/protocols.md):

- **On enable**: `cotype open FILE --json` → store `base_sha`
  buffer-locally; reload buffer from `base_path`. Reloading guarantees
  the buffer matches what cotype believes the base is, closing the
  SPEC's "forbidden protocol" race window between vim reading the file
  and our `cotype open` call.
- **On save**: `BufWriteCmd` overrides the default file write. The
  buffer is piped through `cotype save --base-sha <captured>
  --actor vim --json`; the four outcomes (`direct` / `merged` / `noop` /
  `conflict`) drive a `:edit!` reload when the file has changed.
- **On conflict**: `cotype save` rewrote FILE with diff3 markers; the
  buffer is reloaded so the user sees those markers in place. After
  the user edits them out, `:CotypeResolve` writes the buffer to disk
  via `writefile()` (bypassing `BufWriteCmd`, which would be rejected
  with `ConflictPending`) and calls `cotype resolve` to clear the
  pending state.

## Manual smoke test

The plugin has no automated test suite (would require vim in CI).
Verify it by hand:

```bash
mkdir -p /tmp/cotype-vim && cd /tmp/cotype-vim
echo "hello" > note.txt
cotype init note.txt --json

vim -Nu NONE -c "source /path/to/cotype/editors/vim/plugin/cotype.vim" \
       -c "set autoread" note.txt
```

In vim:

1. `:CotypeMode` → echo area shows `cotype-mode enabled`, the buffer is
   reloaded from the captured base, cursor stays where it was.
2. Edit, then `:w` → echo area: `cotype: saved (direct)`.
3. From a separate shell: `printf 'concurrent\n' > note.txt`. Back in
   vim, edit again and save → `cotype: saved (merged)` (or `conflict`
   if your edit overlaps).

## Known limitations

- No automated tests.
- No suppression of vim's "file changed" warning when the buffer is
  modified at external-write time. See *Concurrent writes* above.
- Tramp-style remote files: untested. The CLI invocation is local-only.
