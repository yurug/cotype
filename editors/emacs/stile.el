;;; stile.el --- Emacs integration for stile  -*- lexical-binding: t; -*-

;; Copyright (c) 2026 Yann Régis-Gianas
;; SPDX-License-Identifier: MIT

;; Author: Yann Régis-Gianas <yann@regis-gianas.org>
;; URL: https://github.com/yurug/stile
;; Package-Requires: ((emacs "27.1"))
;; Version: 0.2.0
;; Keywords: tools, files, vc

;;; Commentary:

;; A minor mode that routes Emacs file saves through `stile' so that a
;; file can be edited concurrently by the user, AI agents, and other
;; processes without lost updates.
;;
;; The protocol implemented here mirrors `kb/spec/protocols.md' in the
;; main stile repository: on activation we run `stile open' and reload
;; the buffer from the returned `base_path' (avoiding the SPEC's
;; "forbidden protocol" race), and on save we pipe the buffer through
;; `stile save --base-sha <captured>' instead of writing the file
;; directly.
;;
;; Setup:
;;   (require 'stile)
;;   ;; Optional: auto-enable on files that already have a sidecar.
;;   (add-hook 'find-file-hook #'stile-maybe-enable)
;;
;; Interactive entry points:
;;   M-x stile-init     start managing the current buffer
;;   M-x stile-mode     toggle the minor mode for this buffer
;;   M-x stile-status   echo the current stile status
;;   M-x stile-resolve  after editing out the diff3 conflict markers

;;; Code:

(require 'json)

(defgroup stile nil
  "Concurrent text-file editing via the stile CLI."
  :group 'tools
  :prefix "stile-")

(defcustom stile-executable "stile"
  "Path to the stile CLI."
  :type 'string :group 'stile)

(defcustom stile-actor "emacs"
  "Default --actor label sent on `stile save'."
  :type 'string :group 'stile)

(defcustom stile-auto-revert t
  "If non-nil, `stile-mode' turns on `auto-revert-mode' in its buffers.

When another actor (an agent, a formatter) writes the file via stile,
auto-revert reloads the buffer silently instead of Emacs nagging
\"task.md changed on disk; really edit buffer?\".  After each revert,
`stile-mode' also re-runs `stile open' so the buffer-local `base_sha'
matches what is now on disk."
  :type 'boolean :group 'stile)

(defvar-local stile--base-sha nil
  "Buffer-local base_sha returned by the most recent `stile open'.")

(defvar-local stile--enabled-auto-revert nil
  "Non-nil if `stile-mode' enabled `auto-revert-mode' here itself.
We track this so that disabling `stile-mode' only undoes the
auto-revert state we set up, not a user's pre-existing setting.")


;; -- supersession-warning suppression --------------------------------------

;; When an agent writes the file via stile, the buffer's recorded modtime
;; lags the file's actual mtime until auto-revert (or our own programmatic
;; revert) catches up. If the user types in that window, Emacs fires
;; `ask-user-about-supersession-threat' -- the "FILE has changed since
;; visited; really edit?" prompt. In a stile-mode buffer that prompt is
;; pure noise: stile's 3-way merge already coordinates concurrent saves,
;; and the buffer will auto-revert on the next file-notify tick.
;;
;; We suppress the prompt by advising the threat function to refresh the
;; visited-file-modtime instead, only for stile-mode buffers.

(defun stile--silence-supersession (orig &rest args)
  "Refresh visited-file-modtime instead of prompting in stile-mode buffers.
Falls through to ORIG (the upstream supersession-threat handler) for
buffers that don't have `stile-mode' on -- we don't want to silence
warnings globally. ARGS is forwarded as-is so we stay compatible with
whatever signature Emacs uses for this function across versions."
  (if (and (boundp 'stile-mode) stile-mode (buffer-file-name))
      (set-visited-file-modtime)
    (apply orig args)))

(advice-add 'ask-user-about-supersession-threat :around
            #'stile--silence-supersession)

(defun stile--refresh-modtime-before-basic-save (orig &rest args)
  "Refresh `visited-file-modtime' before `basic-save-buffer' checks it.
Without this, C-x C-s in a stile-mode buffer whose file was just
written by an agent triggers the standard `FILE has changed since
visited or saved.  Save anyway?' prompt -- because `basic-save-buffer'
calls `verify-visited-file-modtime' BEFORE running
`write-contents-functions', so our `stile--save-via-stile' hook can't
suppress it from inside.

stile coordinates concurrent saves through its 3-way merge; the
mismatch is expected and the prompt is pure friction. Bumping the
recorded modtime to the file's actual mtime makes the check pass and
hands control to the save hooks where stile takes over."
  (when (and (boundp 'stile-mode) stile-mode (buffer-file-name))
    (set-visited-file-modtime))
  (apply orig args))

(advice-add 'basic-save-buffer :around
            #'stile--refresh-modtime-before-basic-save)


;; -- low-level subprocess helpers -------------------------------------------

(defun stile--call-json (&rest args)
  "Run `stile-executable' with ARGS; return (EXIT . PARSED-OR-NIL)."
  (with-temp-buffer
    (let ((exit (apply #'call-process stile-executable nil t nil args)))
      (goto-char (point-min))
      (cons exit
            (and (> (buffer-size) 0)
                 (ignore-errors
                   (json-parse-buffer :object-type 'plist
                                      :null-object nil)))))))

(defun stile--call-with-stdin-json (input &rest args)
  "Run `stile-executable' with ARGS, piping INPUT on stdin; parse JSON.
Return (EXIT . PARSED-OR-NIL)."
  (let ((output-buf (generate-new-buffer " *stile-out*")))
    (unwind-protect
        (let ((exit (with-temp-buffer
                      (insert input)
                      (apply #'call-process-region
                             (point-min) (point-max)
                             stile-executable nil output-buf nil args))))
          (cons exit
                (with-current-buffer output-buf
                  (goto-char (point-min))
                  (and (> (buffer-size) 0)
                       (ignore-errors
                         (json-parse-buffer :object-type 'plist
                                            :null-object nil))))))
      (kill-buffer output-buf))))

(defun stile--sidecar-dir (file)
  "Return FILE's sidecar dir if it exists on disk, else nil."
  (let ((s (expand-file-name
            (concat "." (file-name-nondirectory file) ".stile")
            (file-name-directory file))))
    (and (file-directory-p s) s)))


;; -- core actions -----------------------------------------------------------

(defun stile--reload-buffer-from (path)
  "Replace current buffer's contents with the bytes at PATH.
Used after `stile open' so the buffer matches what stile captured as the
base, avoiding the SPEC's `forbidden protocol' race (read FILE -> later
stile open FILE)."
  (let ((pos (point))
        (inhibit-read-only t)
        (buffer-undo-list t))
    (erase-buffer)
    (insert-file-contents path)
    (goto-char (min pos (point-max)))
    (set-buffer-modified-p nil)
    (set-visited-file-modtime)))

(defun stile--ensure-auto-revert ()
  "Re-enable `auto-revert-mode' if it slipped off.
Emacs's `revert-buffer' with `preserve-modes=t' only protects the major
mode plus a hand-coded list of minors (font-lock, enriched). Arbitrary
minor modes like `auto-revert-mode' are silently disabled by every
programmatic revert -- including the one we issue from
`stile--save-via-stile' on conflict. Call this whenever we've just
reverted the buffer ourselves, and from `after-revert-hook' as a belt
to the suspenders."
  (when (and stile-mode stile-auto-revert
             (not (bound-and-true-p auto-revert-mode)))
    (auto-revert-mode 1)))

(defun stile--refresh-base-sha ()
  "Re-run `stile open' to refresh `stile--base-sha' WITHOUT touching the buffer.
Hook target for `after-revert-hook': auto-revert has just reloaded the
buffer from disk, so we just need a fresh base_sha for subsequent saves.
Also re-arms `auto-revert-mode' in case the revert killed it."
  (when (and stile-mode (buffer-file-name))
    (stile--ensure-auto-revert)
    (let* ((resp (stile--call-json "open" (buffer-file-name) "--json"))
           (data (cdr resp)))
      (when data
        (setq stile--base-sha (plist-get data :base_sha))))))

(defun stile--open-current-buffer ()
  "Run `stile open' on the buffer's file and reload from base_path.
Refuse to clobber unsaved edits."
  (unless (buffer-file-name)
    (user-error "Buffer has no associated file"))
  (when (buffer-modified-p)
    (user-error "stile-mode: buffer has unsaved changes; save or revert first"))
  (let* ((file (buffer-file-name))
         (resp (stile--call-json "open" file "--json"))
         (exit (car resp))
         (data (cdr resp)))
    (unless (zerop exit)
      (user-error "stile open failed: %s"
                  (or (and data (plist-get data :message)) "?")))
    (setq stile--base-sha (plist-get data :base_sha))
    (let ((bp (plist-get data :base_path)))
      (when (and bp (file-readable-p bp))
        (stile--reload-buffer-from bp)))
    (when (eq t (plist-get data :conflicted))
      (let* ((pc (plist-get data :pending_conflict))
             (cp (and pc (plist-get pc :path))))
        (message "stile: pending conflict at %s; resolve before saving" cp)))
    data))

(defun stile--save-via-stile ()
  "Write the buffer through `stile save'.
Intended for `write-contents-functions': returns non-nil to suppress
Emacs' default file-write."
  (unless stile--base-sha
    (user-error "stile-mode: no base captured (toggle stile-mode again)"))
  (let* ((file (buffer-file-name))
         (input (buffer-substring-no-properties (point-min) (point-max)))
         (resp (stile--call-with-stdin-json
                input
                "save" file
                "--base-sha" stile--base-sha
                "--actor" stile-actor
                "--json"))
         (exit (car resp))
         (data (cdr resp))
         (status (and data (plist-get data :status))))
    (cond
     ((string= status "saved")
      (let ((mode (plist-get data :mode))
            (sha  (plist-get data :sha)))
        (setq stile--base-sha sha)
        ;; For mode=merged, FILE differs from what we sent; reload it.
        (when (string= mode "merged")
          (revert-buffer t t t)
          (stile--ensure-auto-revert))
        (set-buffer-modified-p nil)
        (set-visited-file-modtime)
        (message "stile: saved (%s)" mode)
        t))
     ((string= status "conflict")
      ;; FILE now contains diff3 conflict markers. Reload it so the user
      ;; sees and edits the markers in this very buffer; after editing,
      ;; M-x stile-resolve clears the pending state.
      (let ((cid (plist-get data :conflict_id))
            (sha (plist-get data :markers_sha)))
        (revert-buffer t t t)
        ;; revert-buffer with preserve-modes=t still kills auto-revert.
        (stile--ensure-auto-revert)
        (when sha (setq stile--base-sha sha))
        (set-buffer-modified-p nil)
        (set-visited-file-modtime)
        (message "stile: conflict %s -- edit out markers, then M-x stile-resolve"
                 (and cid (substring cid 0 8)))
        t))
     ((string= status "error")
      (message "stile: %s: %s"
               (plist-get data :error)
               (plist-get data :message))
      ;; Buffer stays modified; user can fix and retry.
      t)
     (t
      (message "stile: unexpected response (exit %d)" exit)
      t))))


;; -- interactive commands ---------------------------------------------------

;;;###autoload
(defun stile-init ()
  "Run `stile init' on the current buffer's file and enable `stile-mode'."
  (interactive)
  (unless (buffer-file-name)
    (user-error "Buffer has no associated file"))
  (when (buffer-modified-p)
    (user-error "Save the buffer first; stile-init must see the file on disk"))
  (let* ((resp (stile--call-json "init" (buffer-file-name) "--json"))
         (exit (car resp))
         (data (cdr resp)))
    (unless (zerop exit)
      (user-error "stile init failed: %s"
                  (or (and data (plist-get data :message)) "?"))))
  (stile-mode 1)
  (message "stile: initialised"))

;;;###autoload
(defun stile-status ()
  "Echo the current stile status of the buffer's file."
  (interactive)
  (unless (buffer-file-name)
    (user-error "Buffer has no associated file"))
  (let* ((resp (stile--call-json "status" (buffer-file-name) "--json"))
         (data (cdr resp))
         (status (and data (plist-get data :status))))
    (message "stile: %s" (or status "?"))))

;;;###autoload
(defun stile-resolve ()
  "Clear the pending conflict by accepting the buffer's current contents.
Run this after editing out the diff3 `<<<<<<<' / `>>>>>>>' markers.
The buffer is unconditionally written to disk first (bypassing the
ordinary `stile save' path, which would be rejected while a conflict
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
    (let* ((resp (stile--call-json "resolve" file "--json"))
           (exit (car resp))
           (data (cdr resp)))
      (if (zerop exit)
          (progn
            (setq stile--base-sha (and data (plist-get data :sha)))
            (message "stile: resolved"))
        (message "stile: %s"
                 (or (and data (plist-get data :message)) "resolve failed"))))))


;; -- the minor mode --------------------------------------------------------

;;;###autoload
(define-minor-mode stile-mode
  "Route saves of this buffer through `stile'.

When enabled, \\[save-buffer] invokes `stile save' instead of writing
FILE directly. On activation, the buffer is reloaded from the base
snapshot stile captured, so what the user sees is exactly what stile
believes the base to be.

On conflict, FILE is rewritten with diff3 markers and the buffer is
reverted to show them; edit out the markers and clear the pending
state with \\[stile-resolve]."
  :lighter " stile"
  (cond
   (stile-mode
    (cond
     ((not (buffer-file-name))
      (message "stile-mode: buffer has no file; not enabling"))
     ((buffer-modified-p)
      (message "stile-mode: buffer has unsaved changes; not enabling"))
     (t
      (add-hook 'write-contents-functions
                #'stile--save-via-stile nil 'local)
      ;; Co-edit hygiene: agents writing the file should appear in the
      ;; buffer automatically, not as a "changed on disk" prompt.  The
      ;; after-revert-hook keeps stile--base-sha in step with disk.
      (when (and stile-auto-revert
                 (not (bound-and-true-p auto-revert-mode)))
        (auto-revert-mode 1)
        (setq stile--enabled-auto-revert t))
      (add-hook 'after-revert-hook #'stile--refresh-base-sha nil 'local)
      (stile--open-current-buffer))))
   (t
    (remove-hook 'write-contents-functions
                 #'stile--save-via-stile 'local)
    (remove-hook 'after-revert-hook #'stile--refresh-base-sha 'local)
    (when stile--enabled-auto-revert
      (auto-revert-mode -1)
      (setq stile--enabled-auto-revert nil))
    (kill-local-variable 'stile--base-sha))))

;;;###autoload
(defun stile-maybe-enable ()
  "Enable `stile-mode' if the visited file has a sidecar dir.
Add to `find-file-hook' to opt into automatic activation."
  (when (and (buffer-file-name)
             (stile--sidecar-dir (buffer-file-name)))
    (stile-mode 1)))

(provide 'stile)
;;; stile.el ends here
