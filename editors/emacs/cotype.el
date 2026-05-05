;;; cotype.el --- Concurrent safe-save for shared text files  -*- lexical-binding: t; -*-

;; Copyright (c) 2026 Yann Régis-Gianas
;; SPDX-License-Identifier: MIT

;; Author:     Yann Régis-Gianas <yann@regis-gianas.org>
;; Maintainer: Yann Régis-Gianas <yann@regis-gianas.org>
;; Assisted-by: Claude:claude-opus-4-7
;; URL:        https://github.com/yurug/cotype
;; Package-Requires: ((emacs "27.1"))
;; Version: 0.2.1
;; Keywords: tools, files, vc

;;; Commentary:

;; A minor mode that routes Emacs file saves through `cotype' so that a
;; file can be edited concurrently by the user, AI agents, and other
;; processes without lost updates.
;;
;; The protocol implemented here mirrors `kb/spec/protocols.md' in the
;; main cotype repository: on activation we run `cotype open' and reload
;; the buffer from the returned `base_path' (avoiding the SPEC's
;; "forbidden protocol" race), and on save we pipe the buffer through
;; `cotype save --base-sha <captured>' instead of writing the file
;; directly.
;;
;; Setup:
;;   (require 'cotype)
;;   ;; Optional: auto-enable on files that already have a sidecar.
;;   (add-hook 'find-file-hook #'cotype-maybe-enable)
;;
;; Interactive entry points:
;;   M-x cotype-init     start managing the current buffer
;;   M-x cotype-mode     toggle the minor mode for this buffer
;;   M-x cotype-status   echo the current cotype status
;;   M-x cotype-resolve  after editing out the diff3 conflict markers

;;; Code:

(require 'json)

(defgroup cotype nil
  "Concurrent text-file editing via the cotype CLI."
  :group 'tools
  :prefix "cotype-")

(defcustom cotype-executable "cotype"
  "Path to the cotype CLI."
  :type 'string :group 'cotype)

(defcustom cotype-actor "emacs"
  "Default --actor label sent on `cotype save'."
  :type 'string :group 'cotype)

(defcustom cotype-auto-revert t
  "If non-nil, `cotype-mode' turns on `auto-revert-mode' in its buffers.

When another actor (an agent, a formatter) writes the file via cotype,
auto-revert reloads the buffer silently instead of Emacs nagging
\"task.md changed on disk; really edit buffer?\".  After each revert,
`cotype-mode' also re-runs `cotype open' so the buffer-local `base_sha'
matches what is now on disk."
  :type 'boolean :group 'cotype)

(defvar-local cotype--base-sha nil
  "Buffer-local base_sha returned by the most recent `cotype open'.")

(defvar-local cotype--enabled-auto-revert nil
  "Non-nil if `cotype-mode' enabled `auto-revert-mode' here itself.
We track this so that disabling `cotype-mode' only undoes the
auto-revert state we set up, not a user's pre-existing setting.")

;; Forward declaration: `cotype-mode' is created by the
;; `define-minor-mode' form near the bottom of this file, but several
;; helpers above reference the buffer-local variable.  Without this
;; declaration the byte-compiler emits "reference to free variable"
;; warnings.
(defvar cotype-mode)


;; -- supersession-warning suppression --------------------------------------

;; When an agent writes the file via cotype, the buffer's recorded modtime
;; lags the file's actual mtime until auto-revert (or our own programmatic
;; revert) catches up. If the user types in that window, Emacs fires
;; `ask-user-about-supersession-threat' -- the "FILE has changed since
;; visited; really edit?" prompt. C-x C-s hits a separate, equivalent
;; check inside `basic-save-buffer'. In a cotype-mode buffer both
;; prompts are pure noise: cotype's 3-way merge already coordinates
;; concurrent saves, and the buffer will auto-revert on the next
;; file-notify tick.
;;
;; The advices below short-circuit both checks for cotype-mode buffers
;; only; non-cotype buffers fall through to the upstream behaviour
;; unchanged. The advice is installed lazily on the first cotype-mode
;; activation (idempotent), to avoid modifying Emacs core at file load
;; time even when no buffer ever uses the mode.

(defun cotype--silence-supersession (orig &rest args)
  "Refresh visited-file-modtime instead of prompting in cotype-mode buffers.
Falls through to ORIG (the upstream supersession-threat handler) for
buffers that don't have `cotype-mode' on -- we don't want to silence
warnings globally. ARGS is forwarded as-is so we stay compatible with
whatever signature Emacs uses for this function across versions."
  (if (and (boundp 'cotype-mode) cotype-mode (buffer-file-name))
      (set-visited-file-modtime)
    (apply orig args)))

(defun cotype--refresh-modtime-before-basic-save (orig &rest args)
  "Refresh `visited-file-modtime' before `basic-save-buffer' checks it.
Without this, C-x C-s in a cotype-mode buffer whose file was just
written by an agent triggers the standard \"FILE has changed since
visited or saved.  Save anyway?\" prompt -- because `basic-save-buffer'
calls `verify-visited-file-modtime' BEFORE running
`write-contents-functions', so our `cotype--save-via-cotype' hook
can't suppress it from inside.

ORIG is the wrapped `basic-save-buffer'; ARGS are forwarded
unchanged.  Non-cotype buffers fall through directly to ORIG."
  (when (and (boundp 'cotype-mode) cotype-mode (buffer-file-name))
    (set-visited-file-modtime))
  (apply orig args))

(defvar cotype--global-advice-installed nil
  "Non-nil once `cotype-mode' has installed its modtime-prompt advices.
The advices are installed on first `cotype-mode' activation and left
in place; `advice-add' is idempotent on the same function reference,
so we only need to do this once per Emacs session.")

(defun cotype--install-global-advice ()
  "Install the modtime-prompt-suppression advices.  Idempotent."
  (unless cotype--global-advice-installed
    (advice-add 'ask-user-about-supersession-threat :around
                #'cotype--silence-supersession)
    (advice-add 'basic-save-buffer :around
                #'cotype--refresh-modtime-before-basic-save)
    (setq cotype--global-advice-installed t)))


;; -- low-level subprocess helpers -------------------------------------------

(defun cotype--call-json (&rest args)
  "Run `cotype-executable' with ARGS; return (EXIT . PARSED-OR-NIL)."
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
Return (EXIT . PARSED-OR-NIL)."
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
  "Return FILE's sidecar dir if it exists on disk, else nil."
  (let ((s (expand-file-name
            (concat "." (file-name-nondirectory file) ".cotype")
            (file-name-directory file))))
    (and (file-directory-p s) s)))


;; -- core actions -----------------------------------------------------------

(defun cotype--reload-buffer-from (path)
  "Replace current buffer's contents with the bytes at PATH.
Used after `cotype open' so the buffer matches what cotype captured as the
base, avoiding the SPEC's `forbidden protocol' race (read FILE -> later
cotype open FILE)."
  (let ((pos (point))
        (inhibit-read-only t)
        (buffer-undo-list t))
    (erase-buffer)
    (insert-file-contents path)
    (goto-char (min pos (point-max)))
    (set-buffer-modified-p nil)
    (set-visited-file-modtime)))

(defun cotype--ensure-auto-revert ()
  "Re-enable `auto-revert-mode' if it slipped off.
Emacs's `revert-buffer' with `preserve-modes=t' only protects the major
mode plus a hand-coded list of minors (font-lock, enriched). Arbitrary
minor modes like `auto-revert-mode' are silently disabled by every
programmatic revert -- including the one we issue from
`cotype--save-via-cotype' on conflict. Call this whenever we've just
reverted the buffer ourselves, and from `after-revert-hook' as a belt
to the suspenders."
  (when (and cotype-mode cotype-auto-revert
             (not (bound-and-true-p auto-revert-mode)))
    (auto-revert-mode 1)))

(defun cotype--refresh-base-sha ()
  "Re-run `cotype open' to refresh `cotype--base-sha' WITHOUT touching the buffer.
Hook target for `after-revert-hook': auto-revert has just reloaded the
buffer from disk, so we just need a fresh base_sha for subsequent saves.
Also re-arms `auto-revert-mode' in case the revert killed it."
  (when (and cotype-mode (buffer-file-name))
    (cotype--ensure-auto-revert)
    (let* ((resp (cotype--call-json "open" (buffer-file-name) "--json"))
           (data (cdr resp)))
      (when data
        (setq cotype--base-sha (plist-get data :base_sha))))))

(defun cotype--open-current-buffer ()
  "Run `cotype open' on the buffer's file and reload from base_path.
Refuse to clobber unsaved edits."
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
Intended for `write-contents-functions': returns non-nil to suppress
Emacs' default file-write."
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
      ;; FILE now contains diff3 conflict markers. Reload it so the user
      ;; sees and edits the markers in this very buffer; after editing,
      ;; M-x cotype-resolve clears the pending state.
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
  "Run `cotype init' on the current buffer's file and enable `cotype-mode'."
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
  "Echo the current cotype status of the buffer's file."
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
The buffer is unconditionally written to disk first (bypassing the
ordinary `cotype save' path, which would be rejected while a conflict
is pending), so the CLI sees the user's intended resolution rather
than whatever stale bytes live on disk."
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
    ;; Flush the buffer unconditionally. If buffer == disk, this is a
    ;; no-op write; if disk is stale (e.g. an agent wrote markers
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

;;;###autoload
(define-minor-mode cotype-mode
  "Route saves of this buffer through `cotype'.

When enabled, \\[save-buffer] invokes `cotype save' instead of writing
FILE directly. On activation, the buffer is reloaded from the base
snapshot cotype captured, so what the user sees is exactly what cotype
believes the base to be.

On conflict, FILE is rewritten with diff3 markers and the buffer is
reverted to show them; edit out the markers and clear the pending
state with \\[cotype-resolve]."
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
Add to `find-file-hook' to opt into automatic activation."
  (when (and (buffer-file-name)
             (cotype--sidecar-dir (buffer-file-name)))
    (cotype-mode 1)))

(provide 'cotype)
;;; cotype.el ends here
