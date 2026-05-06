" cotype.vim --- vim/neovim integration for cotype
" Maintainer:  Yann Régis-Gianas <yann@regis-gianas.org>
" Assisted-by: Claude:claude-opus-4-7
" License:     MIT
" Version:     0.1.2
"
" A vim/nvim plugin that routes saves of a cotype-managed file through
" the `cotype' CLI, so the file can be edited concurrently by you, AI
" agents, and other processes without lost updates.
"
" Mental model
" ============
"
" In a cotype-managed buffer, three standard vim concerns get
" redirected through the `cotype' CLI:
"
"   - The bytes vim SHOWS the user are loaded once on enable from
"     `cotype open's `base_path' (NOT from the file directly), so
"     what the buffer holds matches what cotype believes the base
"     to be. Closes the SPEC's "forbidden protocol" race window
"     between the open call and a separate read of FILE.
"   - The bytes vim WRITES go through `cotype save', not the default
"     write-region path. We override `BufWriteCmd' to take over the
"     entire :w action; cotype decides per save whether it's a
"     direct write, a 3-way merge, a noop, or a conflict.
"   - Concurrent writes by other actors trigger an auto-revert via
"     `setlocal autoread' + a `timer_start' periodic poll of
"     `:checktime'. Without the timer we'd only catch external
"     writes when the user happened to type something (CursorHold
"     fires once per idle period, not repeatedly -- see the timer
"     section below for the full story).
"
" Module structure
" ================
"
"   1. Plugin guard + global options.
"   2. Subprocess helpers + small utilities (sidecar dir, buffer-bytes
"      with eol-preservation).
"   3. Core actions: s:Open, s:Save, s:Resolve, s:Status, s:Init.
"   4. Auto-revert timer: a buffer-local repeating `timer_start' that
"      runs `:checktime' regardless of cursor activity.
"   5. s:Enable / s:Disable / s:Toggle / s:MaybeEnable -- the on/off
"      ceremony, plus the autocmd that auto-enables on a managed
"      file's `BufReadPost'.
"   6. The :Cotype* user-visible Ex commands.
"
" Compatibility
" =============
"
" Works in vim >= 8.0 (needs `timer_start' for the auto-revert poll)
" and every neovim. Pure vimscript; no Lua required, no compiled
" extensions. Tested manually against the demos under
" `examples/demo-crepe-nvim/' in the cotype repo.
"
" Setup:
"   :CotypeInit       start managing the current buffer
"   :CotypeMode       toggle the mode for this buffer
"   :CotypeStatus     echo the current cotype state
"   :CotypeResolve    after editing out diff3 markers, clear pending conflict
"
" Auto-enables on buffers whose file has a `.<basename>.cotype/' sidecar
" (set g:cotype_auto_enable = 0 to opt out).

if exists('g:loaded_cotype')
  finish
endif
let g:loaded_cotype = 1


" -- options ------------------------------------------------------------
"
" Each `if !exists' guard means "user-set value wins"; users put the
" `let g:cotype_xxx = ...' lines in their vimrc/init.vim BEFORE the
" plugin loads. Standard vim convention.

if !exists('g:cotype_executable')
  " Path to the `cotype' CLI. Override if cotype lives in a virtualenv
  " that isn't on the user's login PATH.
  let g:cotype_executable = 'cotype'
endif

if !exists('g:cotype_actor')
  " Free-form label sent on `cotype save'. Recorded in conflict
  " meta.json; never affects semantics. Use it to distinguish
  " separate vim sessions on the same file (e.g. `vim:laptop').
  let g:cotype_actor = 'vim'
endif

if !exists('g:cotype_auto_revert')
  " 1 = set up the autoread + timer machinery on enable.  This is
  " what makes external writes (from agents, etc.) appear in the
  " buffer in real time. Turn off if you want to drive `:checktime'
  " manually.
  let g:cotype_auto_revert = 1
endif

if !exists('g:cotype_auto_revert_interval')
  " Timer tick in milliseconds. Smaller = faster detection of agent
  " writes, more `:checktime' calls (each is microseconds).  1000ms
  " is a comfortable default for a chorale at default cadence; 250ms
  " is fine for tight demos.
  let g:cotype_auto_revert_interval = 1000
endif

if !exists('g:cotype_auto_enable')
  " Auto-enable cotype-mode on `BufReadPost' for files that already
  " have a `.<basename>.cotype' sidecar. Set 0 to opt out and call
  " `:CotypeMode' manually.
  let g:cotype_auto_enable = 1
endif


" -- low-level subprocess helpers --------------------------------------
"
" Two `system()'-based wrappers around the cotype CLI. Both return a
" parsed dict (the cotype JSON envelope as a vim Dict) on success or
" `{}' on any failure -- non-zero exit, unparseable stdout, etc.
"
" Returning `{}' uniformly for the failure cases keeps callers simple:
" they check `get(resp, 'status', '')' and react to whatever cotype
" said (or didn't say). Distinguishing "exit non-zero" from "exit 0
" but no JSON" doesn't change what the calling site does next.

function! s:Json(args) abort
  " Run cotype with the given arglist; return parsed JSON or {} on failure.
  let l:cmd = [g:cotype_executable] + a:args
  let l:out = system(l:cmd)
  if v:shell_error != 0
    return {}
  endif
  try
    return json_decode(l:out)
  catch
    " json_decode throws on malformed input; treat that the same as
    " "no useful response" and let the caller's `get(...)' default
    " kick in.
    return {}
  endtry
endfunction

function! s:JsonStdin(args, input) abort
  " Same shape, but pipes `input' on stdin. Used for `cotype save',
  " where the proposed bytes go via stdin while flags go on argv.
  let l:cmd = [g:cotype_executable] + a:args
  let l:out = system(l:cmd, a:input)
  if v:shell_error != 0
    return {}
  endif
  try
    return json_decode(l:out)
  catch
    return {}
  endtry
endfunction

function! s:SidecarDir(file) abort
  " Sidecar dir for FILE: dirname/.basename.cotype.
  " Used by s:MaybeEnable to detect cotype-managed files at find-file
  " time without invoking the CLI -- one isdirectory() check is a lot
  " cheaper than a subprocess.
  let l:dir = fnamemodify(a:file, ':h')
  let l:base = fnamemodify(a:file, ':t')
  return l:dir . '/.' . l:base . '.cotype'
endfunction

function! s:BufferBytes() abort
  " Buffer content as a single string, preserving the file's
  " trailing-eol character if `&eol' is set on this buffer.
  "
  " Why eol matters: if the on-disk file ends with `\n' (the common
  " case), and we send vim's getline()-derived content (which has no
  " trailing newline) to `cotype save', cotype hashes a different
  " byte sequence and treats it as a content change. The `&eol'
  " buffer-local option tracks this; we restore the trailing newline
  " when the option is set.
  let l:content = join(getline(1, '$'), "\n")
  if &eol
    let l:content .= "\n"
  endif
  return l:content
endfunction


" -- core actions -------------------------------------------------------

function! s:Open() abort
  " Run `cotype open' and reload the buffer from `base_path' so the
  " buffer matches what cotype believes the base is. Sets
  " b:cotype_base_sha for subsequent saves.
  "
  " Why we reload from `base_path' (cotype's pinned base bytes) and
  " not from FILE directly: another writer landing between
  " `cotype open' and our read of FILE could slip stale bytes into
  " the buffer without cotype noticing. Loading from base_path
  " closes that race -- those bytes hash to base_sha by construction.
  let l:file = expand('%:p')
  if l:file ==# ''
    echohl ErrorMsg | echom 'cotype: buffer has no file' | echohl None
    return 0
  endif
  let l:resp = s:Json(['open', l:file, '--json'])
  if get(l:resp, 'status', '') !=# 'ok'
    echohl WarningMsg
    echom 'cotype: open failed: ' . get(l:resp, 'message', '?')
    echohl None
    return 0
  endif
  let b:cotype_base_sha = get(l:resp, 'base_sha', '')
  let l:base_path = get(l:resp, 'base_path', '')
  if l:base_path !=# '' && filereadable(l:base_path)
    " Replace buffer with bytes from base_path. `0read' inserts at
    " line 0; we then strip the original lines that are now below
    " the inserted content. The two-step dance (delete first, then
    " 0read) avoids any window where the buffer has the old + new
    " content concatenated.
    let l:pos = getpos('.')
    silent 0,$delete _
    silent execute '0read ' . fnameescape(l:base_path)
    " `0read' leaves an extra empty trailing line; strip it.
    if line('$') > 1 && getline('$') ==# ''
      silent $delete _
    endif
    call setpos('.', l:pos)
    set nomodified
  endif
  if get(l:resp, 'conflicted', v:false) is v:true
    let l:pc = get(l:resp, 'pending_conflict', {})
    echohl WarningMsg
    echom 'cotype: pending conflict at ' . get(l:pc, 'path', '?')
          \ . ' -- :CotypeResolve after editing out markers'
    echohl None
  endif
  return 1
endfunction

function! s:Save() abort
  " Override the default file write: pipe the buffer to `cotype save'
  " and handle the four outcomes (direct / merged / noop / conflict).
  "
  " Branches mirror what the cotype CLI returns. The `merged' and
  " `conflict' cases need a `:edit!' to reload the buffer, because
  " cotype rewrote FILE behind us (with the merged result, or with
  " diff3 markers).  After `:edit!' we `set nomodified' so vim
  " doesn't think the buffer is dirty (it isn't -- we just wrote
  " through cotype).
  if !exists('b:cotype_base_sha') || b:cotype_base_sha ==# ''
    echohl ErrorMsg
    echom 'cotype: no base captured (run :CotypeMode again)'
    echohl None
    return
  endif
  let l:file = expand('%:p')
  let l:content = s:BufferBytes()
  let l:resp = s:JsonStdin(
        \ ['save', l:file,
        \  '--base-sha', b:cotype_base_sha,
        \  '--actor', g:cotype_actor,
        \  '--json'],
        \ l:content)
  let l:status = get(l:resp, 'status', '')

  if l:status ==# 'saved'
    let l:mode = get(l:resp, 'mode', '?')
    let b:cotype_base_sha = get(l:resp, 'sha', b:cotype_base_sha)
    if l:mode ==# 'merged'
      " FILE differs from buffer; reload from disk so the user sees
      " the merged result.
      silent edit!
    endif
    set nomodified
    echo 'cotype: saved (' . l:mode . ')'

  elseif l:status ==# 'conflict'
    " FILE has been rewritten with diff3 markers; reload to show
    " them in the buffer. The user edits them out and runs
    " `:CotypeResolve' to clear the pending state.
    let l:cid = get(l:resp, 'conflict_id', '')
    let l:markers_sha = get(l:resp, 'markers_sha', '')
    silent edit!
    set nomodified
    if l:markers_sha !=# ''
      let b:cotype_base_sha = l:markers_sha
    endif
    echohl WarningMsg
    echom 'cotype: conflict ' . strpart(l:cid, 0, 8) .
          \ ' -- edit out markers, then :CotypeResolve'
    echohl None

  elseif l:status ==# 'error'
    echohl ErrorMsg
    echom 'cotype: ' . get(l:resp, 'error', '?') . ': '
          \ . get(l:resp, 'message', '?')
    echohl None

  else
    " Defensive: an unexpected response shape. Better to log
    " something than to silently swallow.
    echohl WarningMsg
    echom 'cotype: unexpected response from cotype save'
    echohl None
  endif
endfunction

function! s:Resolve() abort
  " Refuse if the buffer still has diff3 markers; otherwise flush the
  " buffer to disk (bypassing the BufWriteCmd hook, which would be
  " rejected with ConflictPending) and run `cotype resolve'.
  "
  " Two safety nets, in order:
  "
  "   1. Search for any `<<<<<<< ' line. If found, jump point to it
  "      and refuse -- the user hasn't finished editing.
  "   2. Flush via `writefile()' (NOT `:w') so we sidestep
  "      `BufWriteCmd', which would otherwise route through cotype
  "      save and be rejected with ConflictPending. After the file
  "      is on disk in clean form, `cotype resolve' does the rest.
  let l:file = expand('%:p')
  if l:file ==# ''
    echohl ErrorMsg | echom 'cotype: buffer has no file' | echohl None
    return
  endif
  let l:line = search('^<<<<<<< ', 'cnw')
  if l:line > 0
    echohl ErrorMsg
    echom 'cotype: buffer still has a conflict marker at line '
          \ . l:line . ' -- edit it out first'
    echohl None
    execute l:line
    return
  endif
  " Flush buffer to disk. `writefile()' bypasses BufWriteCmd entirely.
  " The `&eol ? '' : 'b'' flag preserves vim's view of trailing-newline
  " semantics (writefile adds a final \n unless 'b' flag is set).
  let l:lines = getline(1, '$')
  let l:flags = &eol ? '' : 'b'
  call writefile(l:lines, l:file, l:flags)
  set nomodified
  let l:resp = s:Json(['resolve', l:file, '--json'])
  if get(l:resp, 'status', '') ==# 'resolved'
    let b:cotype_base_sha = get(l:resp, 'sha', b:cotype_base_sha)
    echo 'cotype: resolved'
  else
    echohl ErrorMsg
    echom 'cotype: ' . get(l:resp, 'message', 'resolve failed')
    echohl None
  endif
endfunction

function! s:Status() abort
  " Echo the current cotype state for the buffer's file.
  " One of: unmanaged / clean / conflicted, or `?' on parse failure.
  let l:file = expand('%:p')
  if l:file ==# ''
    echohl ErrorMsg | echom 'cotype: buffer has no file' | echohl None
    return
  endif
  let l:resp = s:Json(['status', l:file, '--json'])
  echo 'cotype: ' . get(l:resp, 'status', '?')
endfunction

function! s:Init() abort
  " Run `cotype init' on the buffer's file and turn the mode on.
  " Idempotent on the CLI side, but we still refuse to call it on a
  " modified buffer: cotype init hashes whatever's on disk, and if
  " the buffer is dirty, the on-disk bytes aren't what the user
  " thinks they're capturing as the base.
  let l:file = expand('%:p')
  if l:file ==# ''
    echohl ErrorMsg | echom 'cotype: buffer has no file' | echohl None
    return
  endif
  if &modified
    echohl ErrorMsg
    echom 'cotype: save the buffer first; cotype init must see the file on disk'
    echohl None
    return
  endif
  let l:resp = s:Json(['init', l:file, '--json'])
  if get(l:resp, 'status', '') ==# 'ok'
    call s:Enable()
    echo 'cotype: initialised'
  else
    echohl ErrorMsg
    echom 'cotype: init failed: ' . get(l:resp, 'message', '?')
    echohl None
  endif
endfunction


" -- auto-revert timer -------------------------------------------------
"
" Why a timer
" -----------
"
" `CursorHold' on its own only fires ONCE after each idle period, not
" repeatedly -- so if the user sits watching the file without
" touching the keyboard, vim never re-checks the file's mtime and
" an external write is invisible until they tap a key. The Emacs
" companion uses `auto-revert-mode' which runs a true periodic
" timer; the vim plugin needs the same shape.
"
" `timer_start' is available in vim >= 8.0 and every neovim, so this
" is portable across the editors that matter. Pre-8.0 vim falls
" back silently to CursorHold-only (see the `exists('*timer_start')'
" guard below).
"
" Buffer association
" ------------------
"
" Timers in vim aren't natively buffer-local. We work around this by
" storing the timer ID in a buffer-local variable
" (`b:cotype_timer_id') and having the callback scan
" `getbufinfo()' to find which buffer's variable matches the firing
" timer. If no buffer claims it (the buffer was unloaded), the timer
" stops itself.
"
" The `BufUnload' autocmd in `s:Enable' is the orderly cleanup path;
" the `getbufinfo' scan is the safety net.

function! s:CheckTimeForTimer(timer) abort
  " Timer callback: find which buffer registered this timer ID and
  " run `:checktime' on it. If no buffer claims it, the timer stops.
  for l:buf in getbufinfo()
    if get(l:buf.variables, 'cotype_timer_id', -1) == a:timer
      execute 'silent! checktime ' . l:buf.bufnr
      return
    endif
  endfor
  " Buffer (or its variable) is gone; stop firing.
  call timer_stop(a:timer)
endfunction

function! s:StartTimer() abort
  " Start a buffer-local repeating timer that calls `:checktime'
  " every `g:cotype_auto_revert_interval' ms.
  if exists('b:cotype_timer_id')
    return
  endif
  if !exists('*timer_start')
    " Pre-8.0 vim without timer support; fall back to CursorHold-only.
    " The CursorHold autocmd in s:Enable does at least catch
    " external writes that land while the user is actively editing.
    return
  endif
  let b:cotype_timer_id = timer_start(
        \ g:cotype_auto_revert_interval,
        \ function('s:CheckTimeForTimer'),
        \ {'repeat': -1})
endfunction

function! s:StopTimer() abort
  " Cancel and forget the buffer-local timer.
  if exists('b:cotype_timer_id')
    if exists('*timer_stop')
      call timer_stop(b:cotype_timer_id)
    endif
    unlet b:cotype_timer_id
  endif
endfunction


" -- enable / disable mode ---------------------------------------------

function! s:Enable() abort
  " Turn cotype-mode on for this buffer.
  "
  "   - Override BufWriteCmd so :w (and any save) routes through
  "     cotype save, not the default write path.
  "   - If g:cotype_auto_revert is on: set autoread, install
  "     CursorHold as a belt-and-suspenders trigger, and start the
  "     repeating timer that drives `:checktime' regardless of
  "     cursor activity.
  "   - Run `cotype open' once to capture the initial base + reload
  "     the buffer from base_path.
  augroup cotype_buffer
    autocmd! * <buffer>
    autocmd BufWriteCmd <buffer> call s:Save()
    if g:cotype_auto_revert
      " Belt to the timer's suspenders: `:checktime' on idle too.
      " CursorHold won't fire while idle, but it does fire briefly
      " AFTER user activity, which catches some edge cases the
      " timer might miss (e.g., a buffer wakeup right after a
      " :stopinsert).
      autocmd CursorHold,CursorHoldI <buffer> silent! checktime
      " If the buffer is unloaded (e.g., :bd), drop the timer so
      " we don't keep firing on a dead buffer.
      autocmd BufUnload <buffer> call s:StopTimer()
    endif
  augroup END
  if g:cotype_auto_revert
    " `set autoread' tells vim it's allowed to silently reload the
    " buffer when the file changes externally AND the buffer is
    " unmodified -- exactly what we want when an agent's save lands.
    setlocal autoread
    " Floor `&updatetime' so the (now belt-and-braces) CursorHold
    " also ticks fast when it does fire. We set it globally rather
    " than `setlocal' because vim's `updatetime' is one of the
    " global-only options; this is a known minor side effect that
    " applies to every buffer in the session.
    if &updatetime > g:cotype_auto_revert_interval
      let &updatetime = g:cotype_auto_revert_interval
    endif
    " The actual periodic poll: a repeating timer that runs
    " `:checktime' on this buffer regardless of cursor activity.
    call s:StartTimer()
  endif
  let b:cotype_enabled = 1
  call s:Open()
endfunction

function! s:Disable() abort
  " Stop intercepting saves and turn off the timer; clear
  " buffer-local state so a future :CotypeMode starts fresh.
  call s:StopTimer()
  augroup cotype_buffer
    autocmd! * <buffer>
  augroup END
  unlet! b:cotype_enabled
  unlet! b:cotype_base_sha
  echo 'cotype-mode disabled'
endfunction

function! s:Toggle() abort
  if get(b:, 'cotype_enabled', 0)
    call s:Disable()
  else
    call s:Enable()
    if get(b:, 'cotype_enabled', 0)
      echo 'cotype-mode enabled'
    endif
  endif
endfunction


" -- maybe-enable on file load ----------------------------------------
"
" Auto-enable cotype-mode when vim opens a file that already has a
" `.<basename>.cotype' sidecar. Detection is by directory presence,
" cheaper than running the CLI; false negatives (e.g., the user
" moved the file away from its sidecar) are recoverable with manual
" `:CotypeMode'.

function! s:MaybeEnable() abort
  let l:file = expand('%:p')
  if l:file !=# '' && isdirectory(s:SidecarDir(l:file))
    call s:Enable()
  endif
endfunction

augroup cotype_global
  autocmd!
  if g:cotype_auto_enable
    autocmd BufReadPost * call s:MaybeEnable()
  endif
augroup END


" -- commands ----------------------------------------------------------
"
" The user-visible Ex commands. Each is a one-line dispatch into the
" private `s:*' functions above; the public-vs-private separation
" keeps internal calls (like s:Init -> s:Enable) from interpreting
" through the command line.

command! CotypeInit    call s:Init()
command! CotypeEnable  call s:Enable()
command! CotypeDisable call s:Disable()
command! CotypeMode    call s:Toggle()
command! CotypeStatus  call s:Status()
command! CotypeResolve call s:Resolve()
