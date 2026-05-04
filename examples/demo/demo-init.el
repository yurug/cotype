;;; Minimal Emacs init for the cotype demo recording.
;;;
;;; - Loads `cotype.el' from ../../editors/emacs/ (path relative to this file).
;;; - Auto-enables `cotype-mode' in any buffer whose file has a cotype sidecar,
;;;   so opening task.md hands control to the integration immediately.
;;; - Speeds up auto-revert so agent-driven file changes show up in the
;;;   buffer within ~half a second (a 15-second recording can't afford the
;;;   default 5-second polling cadence).
;;;
;;; Launch: emacs -nw -Q -l demo-init.el task.md

(setq inhibit-startup-screen t
      initial-scratch-message ""
      ring-bell-function     'ignore
      make-backup-files       nil
      auto-save-default       nil
      auto-revert-verbose     nil
      auto-revert-interval    0.5)

;; Locate cotype.el relative to this init file.
(let* ((init-dir  (file-name-directory load-file-name))
       (cotype-dir (expand-file-name "../../editors/emacs" init-dir)))
  (add-to-list 'load-path cotype-dir))

(require 'cotype)

;; Auto-enable cotype-mode on files that already have a sidecar.
(add-hook 'find-file-hook #'cotype-maybe-enable)

;; Trim chrome that distracts from the file.
(when (fboundp 'menu-bar-mode)   (menu-bar-mode  -1))
(when (fboundp 'tool-bar-mode)   (tool-bar-mode  -1))
(when (fboundp 'scroll-bar-mode) (scroll-bar-mode -1))
(line-number-mode 1)
(column-number-mode 0)

;; Helpers for the puppeteer (which simulates the human user).
;;
;; The richer flow is:
;;    M-x cotype-demo-position-for-spec RET   ;; cursor lands ready to type
;;    <user types the bullet text, char by char>
;;    C-x C-s                                ;; save through cotype-mode
;;
;; That makes the typing visible in the editor pane (one keystroke at a
;; time, paced by the puppeteer's tmux send-keys cadence) and keeps the
;; "user" role explicit on screen.

(defun cotype-demo-position-for-spec ()
  "Move point to a fresh bullet line at the end of `## spec' and insert
the leading \"- \" so the user can type the bullet text immediately.
Does NOT save -- the puppeteer hits `C-x C-s' after typing."
  (interactive)
  (goto-char (point-min))
  (when (re-search-forward "^## spec\\s-*$" nil t)
    (forward-line 1)
    (while (looking-at "^- ")
      (forward-line 1))
    (insert "- ")))

(defun cotype-demo-add-spec (text)
  "One-shot insert -- legacy convenience for the simple-demo flow.
Insert TEXT as a new bullet at the end of `## spec' and save."
  (interactive "sNew spec line: ")
  (save-excursion
    (goto-char (point-min))
    (when (re-search-forward "^## spec\\s-*$" nil t)
      (forward-line 1)
      (while (looking-at "^- ")
        (forward-line 1))
      (insert "- " text "\n")))
  (save-buffer))
