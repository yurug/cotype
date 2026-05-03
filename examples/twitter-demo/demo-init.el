;;; Minimal Emacs init for the stile twitter-demo recording.
;;;
;;; - Loads `stile.el' from ../../editors/emacs/ (path relative to this file).
;;; - Auto-enables `stile-mode' in any buffer whose file has a stile sidecar,
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

;; Locate stile.el relative to this init file.
(let* ((init-dir  (file-name-directory load-file-name))
       (stile-dir (expand-file-name "../../editors/emacs" init-dir)))
  (add-to-list 'load-path stile-dir))

(require 'stile)

;; Auto-enable stile-mode on files that already have a sidecar.
(add-hook 'find-file-hook #'stile-maybe-enable)

;; Trim chrome that distracts from the file.
(when (fboundp 'menu-bar-mode)   (menu-bar-mode  -1))
(when (fboundp 'tool-bar-mode)   (tool-bar-mode  -1))
(when (fboundp 'scroll-bar-mode) (scroll-bar-mode -1))
(line-number-mode 1)
(column-number-mode 0)

;; Helper for the puppeteer: add a bullet at the end of the `## requirements'
;; section and save through stile. The puppeteer just needs to type
;;   M-x stile-demo-add-requirement RET <text> RET
;; to drop a new bullet and save in one keypress sequence.
(defun stile-demo-add-requirement (text)
  "Insert TEXT as a new bullet at the end of the `## requirements' section
of the current buffer, then save through `stile-mode'."
  (interactive "sNew requirement: ")
  (save-excursion
    (goto-char (point-min))
    (when (re-search-forward "^## requirements\\s-*$" nil t)
      ;; Move into the section body.
      (forward-line 1)
      ;; Skip past existing bullet lines.
      (while (looking-at "^- ")
        (forward-line 1))
      ;; Insert the new bullet on a fresh line BEFORE whatever non-bullet
      ;; line we landed on (usually a blank line or the next `## ' header).
      (insert "- " text "\n")))
  (save-buffer))
