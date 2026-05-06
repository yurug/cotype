;;; cotype.el --- Concurrent safe-save for shared text files  -*- lexical-binding: t; -*-

;; Copyright (c) 2026 Yann Régis-Gianas
;; SPDX-License-Identifier: MIT

;; Author:     Yann Régis-Gianas <yann@regis-gianas.org>
;; Maintainer: Yann Régis-Gianas <yann@regis-gianas.org>
;; Assisted-by: Claude:claude-opus-4-7
;; URL:        https://github.com/yurug/cotype
;; Package-Requires: ((emacs "27.1"))
;; Version: 0.2.2
;; Keywords: tools, files, vc

;;; Commentary:

;; A minor mode that routes Emacs file saves through the `cotype' CLI so
;; that a file can be edited concurrently by the user, AI agents, and
;; other processes without lost updates.
;;
;; Mental model
;; ============
;;
;; In a cotype-managed buffer, four standard Emacs concerns get
;; redirected through the `cotype' CLI:
;;
;;   - The bytes Emacs SHOWS the user are loaded once on enable from
;;     `cotype open's `base_path' (NOT from FILE itself), so what we
;;     show matches what cotype believes the base to be.
;;   - The bytes Emacs WRITES go through `cotype save', not through
;;     the default `write-file' path. cotype decides per save whether
;;     it's a clean direct write, a 3-way merge, a noop, or a
;;     conflict.
;;   - Concurrent writes by other actors (agents, formatters,
;;     teammates over SSH) trigger `auto-revert-mode', which reloads
;;     the buffer silently so the user sees the latest version
;;     in real time.
;;   - Two of Emacs's modtime-mismatch prompts that would normally
;;     fire when an external write lands ("FILE has changed since
;;     visited", "Save anyway?") are silenced -- cotype already
;;     coordinates concurrent saves; the prompts are pure noise.
;;
;; The protocol implemented here mirrors `kb/spec/protocols.md' in the
;; cotype repository.  Crucially, `cotype-mode' avoids the SPEC's
;; "forbidden protocol" race: it loads the buffer from the
;; `base_path' returned by `cotype open' rather than separately
;; reading FILE itself, so another writer landing between open and
;; the buffer load cannot slip stale bytes into the buffer.
;;
;; Module structure
;; ================
;;
;;   1. Customisation group + buffer-local state.
;;   2. Forward declaration of `cotype-mode' (the byte-compiler walks
;;      top-to-bottom and helpers below reference the variable that
;;      `define-minor-mode' creates near the end).
;;   3. Supersession-prompt suppression: two `:around' advices on
;;      Emacs core, installed lazily on first cotype-mode activation.
;;      Both check `cotype-mode' before doing anything; non-cotype
;;      buffers see upstream behaviour unchanged.
;;   4. Subprocess helpers: `call-process'-based wrappers that produce
;;      `(EXIT . PARSED-JSON)' tuples so the rest of the file is
;;      pure-elisp glue.
;;   5. Core actions: `cotype--open-current-buffer',
;;      `cotype--save-via-cotype', `cotype--reload-buffer-from'.
;;      Plus the auto-revert ensure helper that re-arms
;;      `auto-revert-mode' after every programmatic revert (Emacs's
;;      `revert-buffer' with preserve-modes=t doesn't preserve it).
;;   6. Interactive commands: `cotype-init', `cotype-status',
;;      `cotype-resolve', plus the `cotype-mode' `define-minor-mode'
;;      itself and the `cotype-maybe-enable' auto-enable predicate.
;;
;; Setup:
;;
;;   (require 'cotype)
;;   ;; Optional: auto-enable on any file that already has a sidecar.
;;   (add-hook 'find-file-hook #'cotype-maybe-enable)
;;
;; Interactive entry points:
;;
;;   M-x cotype-init     start managing the current buffer
;;   M-x cotype-mode     toggle the minor mode for this buffer
;;   M-x cotype-status   echo the current cotype status
;;   M-x cotype-resolve  after editing out the diff3 conflict markers

;;; Code:

(require 'json)


;; -- customisation group + buffer-local state --------------------------

(defgroup cotype nil
  "Concurrent text-file editing via the cotype CLI."
  :group 'tools
  :prefix "cotype-")

(defcustom cotype-executable "cotype"
  "Path to the `cotype' CLI.
Pass an absolute path here if the CLI lives outside `exec-path' --
typical when running cotype from a project virtualenv that isn't on
the user's login PATH."
  :type 'string :group 'cotype)

(defcustom cotype-actor "emacs"
  "Default --actor label sent on `cotype save'.
This string is opaque to cotype; it ends up in the conflict's
`meta.json' if a conflict happens.  Use it to distinguish multiple
emacs sessions if you ever run them on the same file (e.g.
\"emacs:laptop\" vs \"emacs:server\")."
  :type 'string :group 'cotype)

(defcustom cotype-auto-revert t
  "If non-nil, `cotype-mode' turns on `auto-revert-mode' in its buffers.

When another actor (an agent, a formatter, a teammate over SSH)
writes the file via cotype, auto-revert reloads the buffer
silently instead of Emacs nagging \"task.md changed on disk;
really edit buffer?\".  After each revert, `cotype-mode' also
re-runs `cotype open' so the buffer-local `base_sha' matches what
is now on disk -- the next `C-x C-s' carries the right base.

Turn this off if you want to stay in control of revert manually
(unusual; the live-co-edit illusion depends on auto-revert)."
  :type 'boolean :group 'cotype)

(defvar-local cotype--base-sha nil
  "Buffer-local base_sha returned by the most recent `cotype open'.
Refreshed every time we re-open the file (on `cotype-mode' enable
and on every `after-revert-hook' tick).  `cotype-save' uses this
as `--base-sha'; it is the cotype-side identity of the bytes the
buffer was last in sync with.")

(defvar-local cotype--enabled-auto-revert nil
  "Non-nil if `cotype-mode' enabled `auto-revert-mode' here itself.
We track this so that disabling `cotype-mode' only undoes the
auto-revert state we set up, not a user's pre-existing
`auto-revert-mode' setting.  If the user already had auto-revert
on before enabling cotype-mode, leaving it on after disable is the
right thing.")

;; Forward declaration: `cotype-mode' is created by the
;; `define-minor-mode' form near the bottom of this file, but several
;; helpers above reference the buffer-local variable.  Without this
;; declaration the byte-compiler emits "reference to free variable"
;; warnings even though the variable does exist at run time.
(defvar cotype-mode)


;; -- supersession-warning suppression --------------------------------------
;;
;; The story
;; ---------
;;
;; When an agent writes the file via cotype, the buffer's recorded
;; modtime lags the file's actual mtime until auto-revert (or our own
;; programmatic revert) catches up.  Two consequences:
;;
;;   1. If the user TYPES in that window, Emacs fires
;;      `ask-user-about-supersession-threat' -- the
;;      "FILE has changed since visited; really edit?" prompt.
;;
;;   2. If the user SAVES (`C-x C-s') in that window,
;;      `basic-save-buffer' fires its own modtime check BEFORE
;;      `write-contents-functions' runs, asking
;;      "FILE has changed since visited or saved.  Save anyway?".
;;      We can't suppress this from inside `cotype--save-via-cotype'
;;      because the check happens earlier in the call stack.
;;
;; Both prompts are pure noise in cotype-mode buffers: cotype's 3-way
;; merge already coordinates concurrent saves, the buffer will
;; auto-revert on the next file-notify tick, and any genuine
;; conflict surfaces through the inline-marker resolve flow.
;;
;; The fix: two `:around' advices (one per check) that, only in
;; cotype-mode buffers, refresh `visited-file-modtime' silently so
;; the upstream check passes without prompting.  Non-cotype buffers
;; see upstream behaviour unchanged.
;;
;; Lazy install
;; ------------
;;
;; The advices are installed on the first cotype-mode activation in
;; any buffer (via `cotype--install-global-advice'), not at file-load
;; time.  This avoids modifying Emacs core when someone has the
;; package on `load-path' but never enables it.  `advice-add' is
;; idempotent on the same function reference, so installing once per
;; session suffices.

(defun cotype--silence-supersession (orig &rest args)
  "Refresh visited-file-modtime instead of prompting in cotype-mode buffers.

ORIG is the wrapped `ask-user-about-supersession-threat'; ARGS is
forwarded to ORIG unchanged for non-cotype buffers.  In a
cotype-mode buffer we just call `set-visited-file-modtime' (which
synchronises the buffer's recorded mtime to the file's current
mtime) and return -- the user's modification proceeds without a
prompt.

The `&rest args' instead of a fixed `(filename)' signature is
defensive: some Emacs versions added a second argument and we
want one body that works on all of them."
  (if (and (boundp 'cotype-mode) cotype-mode (buffer-file-name))
      (set-visited-file-modtime)
    (apply orig args)))

(defun cotype--refresh-modtime-before-basic-save (orig &rest args)
  "Refresh `visited-file-modtime' before `basic-save-buffer' checks it.

Without this, `C-x C-s' in a cotype-mode buffer whose file was
just written by an agent triggers the standard
\"FILE has changed since visited or saved.  Save anyway?\" prompt
-- because `basic-save-buffer' calls `verify-visited-file-modtime'
BEFORE running `write-contents-functions', so our
`cotype--save-via-cotype' hook can't suppress it from inside.

ORIG is the wrapped `basic-save-buffer'; ARGS are forwarded
unchanged.  Non-cotype buffers fall through directly to ORIG."
  (when (and (boundp 'cotype-mode) cotype-mode (buffer-file-name))
    (set-visited-file-modtime))
  (apply orig args))

(defvar cotype--global-advice-installed nil
  "Non-nil once `cotype-mode' has installed its modtime-prompt advices.
The advices are installed on first `cotype-mode' activation and
left in place; `advice-add' is idempotent on the same function
reference, so we only need to do this once per Emacs session.")

(defun cotype--install-global-advice ()
  "Install the modtime-prompt-suppression advices.  Idempotent.
Called from the `cotype-mode' enable branch the first time the
mode is turned on in any buffer.  See the long comment above
for what the two advices do and why."
  (unless cotype--global-advice-installed
    (advice-add 'ask-user-about-supersession-threat :around
                #'cotype--silence-supersession)
    (advice-add 'basic-save-buffer :around
                #'cotype--refresh-modtime-before-basic-save)
    (setq cotype--global-advice-installed t)))


;; -- low-level subprocess helpers -------------------------------------------
;;
;; Two thin wrappers around `call-process' / `call-process-region'
;; that handle the `cotype --json' shape uniformly.  Every interactive
;; command + every internal hook in this file goes through one of
;; these; there's no other path to the CLI.
;;
;; Both return `(EXIT . PARSED-OR-NIL)':
;;   EXIT       -- the subprocess's exit code as an integer.
;;   PARSED     -- the JSON envelope as a plist (`json-parse-buffer's
;;                 `:object-type 'plist'), or nil if stdout was empty
;;                 or unparseable.
;;
;; Returning the exit code separately from the parsed JSON is
;; deliberate: cotype's contract puts errors in the JSON `status'
;; field, but we still want to distinguish "no JSON came back at
;; all" (exit non-zero, no stdout, parser returns nil) from "JSON
;; came back but says it's an error" (exit non-zero, parsed dict
;; with `:status "error"').

(defun cotype--call-json (&rest args)
  "Run `cotype-executable' with ARGS; return (EXIT . PARSED-OR-NIL).

Used for cotype calls that don't have stdin input -- `init',
`open', `status', `resolve'.  Saves into a temp buffer so the
user's current buffer isn't disturbed."
  (with-temp-buffer
    (let ((exit (apply #'call-process cotype-executable nil t nil args)))
      (goto-char (point-min))
      (cons exit
            (and (> (buffer-size) 0)
                 (ignore-errors
                   (json-parse-buffer :object-type 'plist
                                      :null-object nil)))))))

(defun cotype--call-with-stdin-json (input &rest args)
  "Run `cotype-executable' with ARGS, piping INPUT on stdin; parse JSON.
Return (EXIT . PARSED-OR-NIL).

Used for `cotype save', which takes the proposed bytes on stdin.
The two-buffer dance (`with-temp-buffer' for input, a separate
`output-buf' for stdout) is what `call-process-region' wants:
input comes from a region of the current buffer, output goes to
a named buffer we read afterward.  We `kill-buffer' the output
buffer regardless of success so it doesn't pile up across saves."
  (let ((output-buf (generate-new-buffer " *cotype-out*")))
    (unwind-protect
        (let ((exit (with-temp-buffer
                      (insert input)
                      (apply #'call-process-region
                             (point-min) (point-max)
                             cotype-executable nil output-buf nil args))))
          (cons exit
                (with-current-buffer output-buf
                  (goto-char (point-min))
                  (and (> (buffer-size) 0)
                       (ignore-errors
                         (json-parse-buffer :object-type 'plist
                                            :null-object nil))))))
      (kill-buffer output-buf))))

(defun cotype--sidecar-dir (file)
  "Return FILE's sidecar dir if it exists on disk, else nil.

Used by `cotype-maybe-enable' to detect cotype-managed files at
`find-file' time without invoking the CLI.  The sidecar's name is
fixed by cotype's data model: `dirname/.basename.cotype'."
  (let ((s (expand-file-name
            (concat "." (file-name-nondirectory file) ".cotype")
            (file-name-directory file))))
    (and (file-directory-p s) s)))


;; -- core actions -----------------------------------------------------------

(defun cotype--reload-buffer-from (path)
  "Replace current buffer's contents with the bytes at PATH.

Used after `cotype open' so the buffer matches what cotype
captured as the base, avoiding the SPEC's `forbidden protocol'
race (read FILE -> later cotype open FILE).  If we simply called
`(insert-file-contents file)' here, another writer landing between
`cotype open' and the read could slip stale bytes into the
buffer; reading from PATH (cotype's pinned-bytes copy under
`<sidecar>/bases/<hex>') closes that race.

`buffer-undo-list' is bound to t for the duration of the swap so
the reload doesn't pollute undo history -- the user shouldn't be
able to undo back to a state that pre-dates cotype-mode being
enabled."
  (let ((pos (point))
        (inhibit-read-only t)
        (buffer-undo-list t))
    (erase-buffer)
    (insert-file-contents path)
    ;; Restore point if it was inside the new content; clamp if the
    ;; new buffer is shorter.
    (goto-char (min pos (point-max)))
    (set-buffer-modified-p nil)
    (set-visited-file-modtime)))

(defun cotype--ensure-auto-revert ()
  "Re-enable `auto-revert-mode' if it slipped off.

Emacs's `revert-buffer' with `preserve-modes=t' only protects the
major mode plus a hand-coded list of minors (font-lock, enriched).
Arbitrary minor modes like `auto-revert-mode' are silently
disabled by every programmatic revert -- including the one we
issue from `cotype--save-via-cotype' on conflict and on a merged
save.  Without re-arming, `cotype-mode' would silently lose its
live-update behaviour on the first agent save.

Call this whenever we've just reverted the buffer ourselves, and
from `after-revert-hook' as a belt-and-braces."
  (when (and cotype-mode cotype-auto-revert
             (not (bound-and-true-p auto-revert-mode)))
    (auto-revert-mode 1)))

(defun cotype--refresh-base-sha ()
  "Re-run `cotype open' to refresh `cotype--base-sha' WITHOUT touching the buffer.

Hook target for `after-revert-hook': auto-revert has just
reloaded the buffer from disk, so we just need a fresh base_sha
for subsequent saves.  We do NOT call `cotype--reload-buffer-from'
here -- the buffer is already in sync with disk thanks to
auto-revert; replacing the bytes again would be wasteful and
could surprise undo.

Also re-arms `auto-revert-mode' (`cotype--ensure-auto-revert') in
case the revert killed it."
  (when (and cotype-mode (buffer-file-name))
    (cotype--ensure-auto-revert)
    (let* ((resp (cotype--call-json "open" (buffer-file-name) "--json"))
           (data (cdr resp)))
      (when data
        (setq cotype--base-sha (plist-get data :base_sha))))))

(defun cotype--open-current-buffer ()
  "Run `cotype open' on the buffer's file and reload from base_path.

Refuse to clobber unsaved edits: if the buffer is dirty when this
runs, the user has unsynchronised work in flight, and replacing
their buffer contents would be a data loss.  They have to save
or revert first.

If the file has a pending conflict (cotype's `conflicted: true'
in the response), we still load the marker-laden bytes into the
buffer (so the user can edit out the markers) and emit a
`message' so the modeline / minibuffer shows the situation."
  (unless (buffer-file-name)
    (user-error "Buffer has no associated file"))
  (when (buffer-modified-p)
    (user-error "cotype-mode: buffer has unsaved changes; save or revert first"))
  (let* ((file (buffer-file-name))
         (resp (cotype--call-json "open" file "--json"))
         (exit (car resp))
         (data (cdr resp)))
    (unless (zerop exit)
      (user-error "cotype open failed: %s"
                  (or (and data (plist-get data :message)) "?")))
    (setq cotype--base-sha (plist-get data :base_sha))
    (let ((bp (plist-get data :base_path)))
      (when (and bp (file-readable-p bp))
        (cotype--reload-buffer-from bp)))
    (when (eq t (plist-get data :conflicted))
      (let* ((pc (plist-get data :pending_conflict))
             (cp (and pc (plist-get pc :path))))
        (message "cotype: pending conflict at %s; resolve before saving" cp)))
    data))

(defun cotype--save-via-cotype ()
  "Write the buffer through `cotype save'.

Intended as a `write-contents-functions' member: returns non-nil
to suppress Emacs' default file-write.

Branches on the four cotype save outcomes:

  - saved (direct/noop)  -- cotype wrote our bytes (or detected
                            equality with what's already there).
                            Update `cotype--base-sha', clear modified,
                            done.
  - saved (merged)       -- cotype wrote a 3-way-merged result that
                            differs from what we sent.  Reload the
                            buffer so the user sees the merged
                            content.  `revert-buffer' kills
                            auto-revert (preserve-modes=t doesn't
                            protect arbitrary minors), so re-arm.
  - conflict             -- cotype wrote diff3 markers into FILE.
                            Reload the buffer so the user sees the
                            markers in place; same revert / re-arm
                            song.  The markers' sha becomes our new
                            base_sha so a subsequent C-x C-s after
                            the user has hand-resolved (without
                            running M-x cotype-resolve) at least
                            uses the right base.
  - error                -- log the error, leave the buffer dirty,
                            return non-nil so Emacs doesn't try its
                            own write.  The user can fix and retry.

Returning t for the unexpected-response branch is defensive: an
unrecognised payload is still preferable to a fall-through to
Emacs' default write, which would bypass cotype entirely."
  (unless cotype--base-sha
    (user-error "cotype-mode: no base captured (toggle cotype-mode again)"))
  (let* ((file (buffer-file-name))
         (input (buffer-substring-no-properties (point-min) (point-max)))
         (resp (cotype--call-with-stdin-json
                input
                "save" file
                "--base-sha" cotype--base-sha
                "--actor" cotype-actor
                "--json"))
         (exit (car resp))
         (data (cdr resp))
         (status (and data (plist-get data :status))))
    (cond
     ((string= status "saved")
      (let ((mode (plist-get data :mode))
            (sha  (plist-get data :sha)))
        (setq cotype--base-sha sha)
        ;; For mode=merged, FILE differs from what we sent; reload it.
        (when (string= mode "merged")
          (revert-buffer t t t)
          (cotype--ensure-auto-revert))
        (set-buffer-modified-p nil)
        (set-visited-file-modtime)
        (message "cotype: saved (%s)" mode)
        t))
     ((string= status "conflict")
      ;; FILE now contains diff3 conflict markers.  Reload it so the
      ;; user sees and edits the markers in this very buffer; after
      ;; editing, M-x cotype-resolve clears the pending state.
      (let ((cid (plist-get data :conflict_id))
            (sha (plist-get data :markers_sha)))
        (revert-buffer t t t)
        ;; revert-buffer with preserve-modes=t still kills auto-revert.
        (cotype--ensure-auto-revert)
        (when sha (setq cotype--base-sha sha))
        (set-buffer-modified-p nil)
        (set-visited-file-modtime)
        (message "cotype: conflict %s -- edit out markers, then M-x cotype-resolve"
                 (and cid (substring cid 0 8)))
        t))
     ((string= status "error")
      (message "cotype: %s: %s"
               (plist-get data :error)
               (plist-get data :message))
      ;; Buffer stays modified; user can fix and retry.
      t)
     (t
      (message "cotype: unexpected response (exit %d)" exit)
      t))))


;; -- interactive commands ---------------------------------------------------

;;;###autoload
(defun cotype-init ()
  "Run `cotype init' on the current buffer's file and enable `cotype-mode'.

`cotype init' is idempotent on the CLI side, but we still refuse
to call it on a buffer with unsaved edits -- the CLI hashes
whatever's on disk, and a dirty buffer means the on-disk bytes
aren't what the user thinks they're capturing as the base."
  (interactive)
  (unless (buffer-file-name)
    (user-error "Buffer has no associated file"))
  (when (buffer-modified-p)
    (user-error "Save the buffer first; cotype-init must see the file on disk"))
  (let* ((resp (cotype--call-json "init" (buffer-file-name) "--json"))
         (exit (car resp))
         (data (cdr resp)))
    (unless (zerop exit)
      (user-error "cotype init failed: %s"
                  (or (and data (plist-get data :message)) "?"))))
  (cotype-mode 1)
  (message "cotype: initialised"))

;;;###autoload
(defun cotype-status ()
  "Echo the current cotype status of the buffer's file.

One of `unmanaged', `clean', `conflicted', or `?' if the CLI's
response was unparseable.  Useful as a quick sanity check when
the modeline doesn't show what you expect."
  (interactive)
  (unless (buffer-file-name)
    (user-error "Buffer has no associated file"))
  (let* ((resp (cotype--call-json "status" (buffer-file-name) "--json"))
         (data (cdr resp))
         (status (and data (plist-get data :status))))
    (message "cotype: %s" (or status "?"))))

;;;###autoload
(defun cotype-resolve ()
  "Clear the pending conflict by accepting the buffer's current contents.

Run this after editing out the diff3 `<<<<<<<' / `>>>>>>>' markers.

Two safety nets, in order:

  1. Refuse if the buffer still has a `<<<<<<< ' line.  Jump
     point to the first remaining marker so the user can fix it
     and try again.
  2. Flush the buffer to disk via `write-region' (with
     `write-contents-functions' temporarily nil so our save hook
     does NOT run), THEN call `cotype resolve'.  Why this order:
     the ordinary `cotype save' path is rejected with
     `ConflictPending' while a conflict is pending, so we have to
     bypass it; once disk reflects the user's resolution, `cotype
     resolve' validates and accepts."
  (interactive)
  (unless (buffer-file-name)
    (user-error "Buffer has no associated file"))
  (let ((file (buffer-file-name)))
    ;; Refuse if the user hasn't finished editing -- jump point to the
    ;; first remaining marker so they can fix it.
    (save-excursion
      (goto-char (point-min))
      (when (re-search-forward "^<<<<<<< " nil t)
        (let ((line (line-number-at-pos (match-beginning 0))))
          (goto-char (match-beginning 0))
          (user-error
           "Buffer still has a conflict marker at line %d -- edit it out first"
           line))))
    ;; Flush the buffer unconditionally.  If buffer == disk, this is
    ;; a no-op write; if disk is stale (e.g. an agent wrote markers
    ;; between the user opening the file and this command), the
    ;; user's buffer is the truth.
    (let ((write-contents-functions nil))
      (write-region (point-min) (point-max) file nil 'no-message))
    (set-buffer-modified-p nil)
    (set-visited-file-modtime)
    (let* ((resp (cotype--call-json "resolve" file "--json"))
           (exit (car resp))
           (data (cdr resp)))
      (if (zerop exit)
          (progn
            (setq cotype--base-sha (and data (plist-get data :sha)))
            (message "cotype: resolved"))
        (message "cotype: %s"
                 (or (and data (plist-get data :message)) "resolve failed"))))))


;; -- the minor mode --------------------------------------------------------
;;
;; The `define-minor-mode' body is the on/off toggle.  Two cases:
;;
;;   ON: install hooks (write-contents-functions, after-revert-hook),
;;       turn on auto-revert if appropriate, lazily install the
;;       global modtime-prompt advices, and run `cotype open' to
;;       capture the first base_sha + reload from base_path.
;;
;;   OFF: remove the hooks and undo the auto-revert state ONLY if we
;;       were the ones who turned auto-revert on.  Drop the
;;       buffer-local base_sha so a subsequent re-enable starts fresh.
;;
;; The on-branch refuses to enable in two situations: no associated
;; file (no point), or the buffer is modified (would lose work on the
;; reload-from-base_path step).  Both produce a `message' but leave
;; the mode flag toggled by `define-minor-mode' itself; toggling it
;; back off is the user's call.

;;;###autoload
(define-minor-mode cotype-mode
  "Route saves of this buffer through `cotype'.

When enabled, \\[save-buffer] invokes `cotype save' instead of
writing FILE directly.  On activation, the buffer is reloaded from
the base snapshot cotype captured, so what the user sees is
exactly what cotype believes the base to be.

On conflict, FILE is rewritten with diff3 markers and the buffer
is reverted to show them; edit out the markers and clear the
pending state with \\[cotype-resolve]."
  :lighter " cotype"
  (cond
   (cotype-mode
    (cond
     ((not (buffer-file-name))
      (message "cotype-mode: buffer has no file; not enabling"))
     ((buffer-modified-p)
      (message "cotype-mode: buffer has unsaved changes; not enabling"))
     (t
      ;; Install the global modtime-prompt advices the first time
      ;; cotype-mode is enabled in any buffer.
      (cotype--install-global-advice)
      (add-hook 'write-contents-functions
                #'cotype--save-via-cotype nil 'local)
      ;; Co-edit hygiene: agents writing the file should appear in the
      ;; buffer automatically, not as a "changed on disk" prompt.  The
      ;; after-revert-hook keeps cotype--base-sha in step with disk.
      (when (and cotype-auto-revert
                 (not (bound-and-true-p auto-revert-mode)))
        (auto-revert-mode 1)
        (setq cotype--enabled-auto-revert t))
      (add-hook 'after-revert-hook #'cotype--refresh-base-sha nil 'local)
      (cotype--open-current-buffer))))
   (t
    (remove-hook 'write-contents-functions
                 #'cotype--save-via-cotype 'local)
    (remove-hook 'after-revert-hook #'cotype--refresh-base-sha 'local)
    (when cotype--enabled-auto-revert
      (auto-revert-mode -1)
      (setq cotype--enabled-auto-revert nil))
    (kill-local-variable 'cotype--base-sha))))

;;;###autoload
(defun cotype-maybe-enable ()
  "Enable `cotype-mode' if the visited file has a sidecar dir.

Add to `find-file-hook' to opt into automatic activation:

    (add-hook \\='find-file-hook #\\='cotype-maybe-enable)

Detection is by sidecar-directory presence (cheap; just a
`file-directory-p' check) rather than by running the CLI -- so
this hook is fast even on `find-file' for unrelated files.  False
negatives (the file IS managed but the sidecar is absent because
the user moved them apart) are recoverable with `M-x cotype-mode'."
  (when (and (buffer-file-name)
             (cotype--sidecar-dir (buffer-file-name)))
    (cotype-mode 1)))

(provide 'cotype)
;;; cotype.el ends here
