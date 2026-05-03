;;; stile.el --- Emacs integration for stile  -*- lexical-binding: t; -*-

;; Copyright (c) 2026 Yann Régis-Gianas
;; SPDX-License-Identifier: MIT

;; Author: Yann Régis-Gianas <yann@regis-gianas.org>
;; URL: https://github.com/yurug/stile
;; Package-Requires: ((emacs "27.1"))
;; Version: 0.1.0
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
;;   M-x stile-init                start managing the current buffer
;;   M-x stile-mode                toggle the minor mode for this buffer
;;   M-x stile-status              echo the current stile status
;;   M-x stile-resolve-use-merged  after editing the merged conflict file

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

(defvar-local stile--base-sha nil
  "Buffer-local base_sha returned by the most recent `stile open'.")


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
          (revert-buffer t t t))
        (set-buffer-modified-p nil)
        (set-visited-file-modtime)
        (message "stile: saved (%s)" mode)
        t))
     ((string= status "conflict")
      (let* ((cp (plist-get data :conflict_path))
             (cid (plist-get data :conflict_id))
             (merged (and cp (expand-file-name "merged" cp))))
        (message "stile: conflict %s -- edit %s, then M-x stile-resolve-use-merged"
                 cid merged)
        (when (and merged (file-readable-p merged))
          (find-file-other-window merged))
        ;; Buffer stays modified (we don't lose user's work).
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
(defun stile-resolve-use-merged ()
  "Resolve the pending conflict using the (presumably edited) merged file.
Run this from the *original* buffer after editing
`<sidecar>/conflicts/<id>/merged' to remove diff3 markers."
  (interactive)
  (unless (buffer-file-name)
    (user-error "Buffer has no associated file"))
  (let* ((resp (stile--call-json
                "resolve" (buffer-file-name) "--use-merged" "--json"))
         (exit (car resp))
         (data (cdr resp)))
    (if (zerop exit)
        (progn
          (revert-buffer t t t)
          (stile--open-current-buffer)
          (message "stile: resolved"))
      (message "stile: %s"
               (or (and data (plist-get data :message)) "resolve failed")))))


;; -- the minor mode --------------------------------------------------------

;;;###autoload
(define-minor-mode stile-mode
  "Route saves of this buffer through `stile'.

When enabled, \\[save-buffer] invokes `stile save' instead of writing
FILE directly. On activation, the buffer is reloaded from the base
snapshot stile captured, so what the user sees is exactly what stile
believes the base to be.

Conflicts open the merged file in another window; resolve with
\\[stile-resolve-use-merged] from this buffer."
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
      (stile--open-current-buffer))))
   (t
    (remove-hook 'write-contents-functions
                 #'stile--save-via-stile 'local)
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
