" demo-init.vim --- minimal neovim config for the cotype crêpe-stand demo.
"
" - Loads the cotype vim plugin from the monorepo (../../editors/vim/).
" - Trims UI chrome so the buffer reads as cleanly as possible in the GIF.
" - Defines `:CotypeDemoPositionForUser', the helper the puppeteer
"   invokes via `<Esc>:CotypeDemoPositionForUser<CR>' to land the
"   cursor on a fresh line at the end of `## user''s content and
"   immediately enter insert mode.
"
" Launch: nvim -u demo-init.vim -i NONE brainstorm.md

" -- UI chrome ----------------------------------------------------------

set nocompatible
set noruler noshowmode noshowcmd
set nonumber norelativenumber nolist
set laststatus=2 statusline=\ cotype-mode\ -\ neovim
set cmdheight=1
set updatetime=300
" Don't write swapfiles into the demo workdir.
set noswapfile

" -- Load the cotype plugin from the monorepo ---------------------------

let s:init_dir = expand('<sfile>:p:h')
execute 'set runtimepath+=' . fnameescape(s:init_dir . '/../../editors/vim')
runtime! plugin/cotype.vim

let g:cotype_actor = 'nvim'
let g:cotype_auto_revert = 1
" Faster CursorHold tick = faster auto-revert detection of agent writes.
let g:cotype_auto_revert_interval = 300

" -- Demo helper for the puppeteer --------------------------------------
"
" Position cursor on a fresh blank line at the end of `## user''s
" content and start insert mode. Mirrors the Emacs companion's
" `cotype-demo-position-for-user'.

function! CotypeDemoPositionForUser() abort
  call cursor(1, 1)
  if search('\v^## user\s*$', 'cW') == 0
    echohl ErrorMsg
    echom 'demo: cannot find ## user section'
    echohl None
    return
  endif
  " Find the next `## ' header (or EOF + 1).
  let l:next = search('\v^## ', 'nW')
  if l:next == 0
    let l:next = line('$') + 1
  endif
  " Walk back over blank lines to the last non-blank line of the user
  " section.
  let l:line = l:next - 1
  while l:line > 0 && getline(l:line) =~# '\v^\s*$'
    let l:line -= 1
  endwhile
  " Insert two blank lines below it; place cursor on the second.
  call append(l:line, ['', ''])
  call cursor(l:line + 2, 1)
  " Begin insert mode after this function returns.
  startinsert
endfunction

command! CotypeDemoPositionForUser call CotypeDemoPositionForUser()
