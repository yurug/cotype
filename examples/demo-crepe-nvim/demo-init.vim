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

" -- Demo helpers for the puppeteer -------------------------------------
"
" The auto-revert timer that the cotype plugin starts on enable
" (`b:cotype_timer_id') ticks `:checktime' every ~1 s regardless of
" cursor activity. That's exactly what we want most of the time -- a
" hands-off viewer sees agent replies live -- but it RACES with the
" puppeteer's typing: by round 2, agents have written to the file, the
" buffer is modified (we just appended blank lines for the user to
" type into), and a checktime tick will either kick vim out of insert
" mode or surface a "file changed" message that swallows the next
" few keys. Symptom: the first few characters of rounds 2 and 3 go
" missing.
"
" Workaround: pause the timer while the puppeteer is in a turn
" (`:CotypeDemoPositionForUser') and resume it once the save lands
" (`:CotypeDemoResumeTimer', chained after `:w`).

function! CotypeDemoPositionForUser() abort
  " Pause auto-revert until the save chain calls Resume.
  if exists('b:cotype_timer_id') && exists('*timer_pause')
    call timer_pause(b:cotype_timer_id, 1)
  endif

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

function! CotypeDemoResumeTimer() abort
  if exists('b:cotype_timer_id') && exists('*timer_pause')
    call timer_pause(b:cotype_timer_id, 0)
  endif
endfunction

command! CotypeDemoPositionForUser call CotypeDemoPositionForUser()
command! CotypeDemoResumeTimer    call CotypeDemoResumeTimer()
