" cotype.vim --- vim/neovim integration for cotype
" Maintainer:  Yann Régis-Gianas <yann@regis-gianas.org>
" Assisted-by: Claude:claude-opus-4-7
" License:     MIT
" Version:     0.1.0
"
" A vim/nvim plugin that routes saves of a cotype-managed file through
" `cotype save', so the file can be edited concurrently by you, AI
" agents, and other processes without lost updates.
"
" Works in both vim (>= 7.4) and neovim (>= 0.5). Pure vimscript; no
" Lua required.
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

if !exists('g:cotype_executable')
  let g:cotype_executable = 'cotype'
endif

if !exists('g:cotype_actor')
  let g:cotype_actor = 'vim'
endif

if !exists('g:cotype_auto_revert')
  let g:cotype_auto_revert = 1
endif

if !exists('g:cotype_auto_revert_interval')
  let g:cotype_auto_revert_interval = 1000  " ms; ceiling on &updatetime
endif

if !exists('g:cotype_auto_enable')
  let g:cotype_auto_enable = 1
endif

" -- low-level subprocess helpers --------------------------------------

" Run cotype with the given arglist; return parsed JSON or {} on failure.
function! s:Json(args) abort
  let l:cmd = [g:cotype_executable] + a:args
  let l:out = system(l:cmd)
  if v:shell_error != 0
    return {}
  endif
  try
    return json_decode(l:out)
  catch
    return {}
  endtry
endfunction

" Same, with `input' piped on stdin.
function! s:JsonStdin(args, input) abort
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

" Sidecar dir for FILE: dirname/.basename.cotype.
function! s:SidecarDir(file) abort
  let l:dir = fnamemodify(a:file, ':h')
  let l:base = fnamemodify(a:file, ':t')
  return l:dir . '/.' . l:base . '.cotype'
endfunction

" Buffer content as a single string, preserving the file's trailing-eol
" character if `&eol' is set on this buffer.
function! s:BufferBytes() abort
  let l:content = join(getline(1, '$'), "\n")
  if &eol
    let l:content .= "\n"
  endif
  return l:content
endfunction

" -- core actions -------------------------------------------------------

" Run `cotype open' and reload the buffer from base_path so the buffer
" matches what cotype believes the base is. Sets b:cotype_base_sha.
function! s:Open() abort
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
    " Replace buffer with bytes from base_path. Use `0read' to insert at
    " line 0, then delete the original lines below the inserted content.
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

" Override the default file write: pipe the buffer to `cotype save' and
" handle the four outcomes (direct / merged / noop / conflict).
function! s:Save() abort
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
      " FILE differs from buffer; reload from disk.
      silent edit!
    endif
    set nomodified
    echo 'cotype: saved (' . l:mode . ')'

  elseif l:status ==# 'conflict'
    " FILE has been rewritten with diff3 markers; reload to show them.
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
    echohl WarningMsg
    echom 'cotype: unexpected response from cotype save'
    echohl None
  endif
endfunction

" Refuse if the buffer still has diff3 markers; otherwise flush the
" buffer to disk (bypassing the BufWriteCmd hook, which would be
" rejected with ConflictPending) and run `cotype resolve'.
function! s:Resolve() abort
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
  let l:file = expand('%:p')
  if l:file ==# ''
    echohl ErrorMsg | echom 'cotype: buffer has no file' | echohl None
    return
  endif
  let l:resp = s:Json(['status', l:file, '--json'])
  echo 'cotype: ' . get(l:resp, 'status', '?')
endfunction

function! s:Init() abort
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

" -- enable / disable mode ---------------------------------------------

function! s:Enable() abort
  augroup cotype_buffer
    autocmd! * <buffer>
    autocmd BufWriteCmd <buffer> call s:Save()
    if g:cotype_auto_revert
      autocmd CursorHold,CursorHoldI <buffer> silent! checktime
    endif
  augroup END
  if g:cotype_auto_revert
    " `set autoread' makes vim silently reload the buffer when the file
    " changes externally AND the buffer is unmodified -- exactly what
    " we want when an agent's save lands.
    setlocal autoread
    " Faster CursorHold tick = faster auto-revert detection.
    if &updatetime > g:cotype_auto_revert_interval
      let &updatetime = g:cotype_auto_revert_interval
    endif
  endif
  let b:cotype_enabled = 1
  call s:Open()
endfunction

function! s:Disable() abort
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

command! CotypeInit    call s:Init()
command! CotypeEnable  call s:Enable()
command! CotypeDisable call s:Disable()
command! CotypeMode    call s:Toggle()
command! CotypeStatus  call s:Status()
command! CotypeResolve call s:Resolve()
