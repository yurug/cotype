;;; Emacs init for the crêpe-stand brainstorming demo recording.
;;;
;;; - Loads `cotype.el' from the monorepo's editors/emacs/ directory.
;;; - Auto-enables `cotype-mode' on the file we're opening, so saves
;;;   route through the cotype CLI and external writes (from the
;;;   headless agents) silently auto-revert into the buffer.
;;; - Speeds up auto-revert so agent saves appear within ~half a
;;;   second; the GIF can't afford the default 5 s polling cadence.
;;; - Defines `cotype-demo-position-for-user' which the puppeteer
;;;   script invokes via `M-x' to drop point into a fresh paragraph
;;;   slot at the end of the `## user' section before typing.

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

;; Trim chrome that distracts from the file content.
(when (fboundp 'menu-bar-mode)   (menu-bar-mode  -1))
(when (fboundp 'tool-bar-mode)   (tool-bar-mode  -1))
(when (fboundp 'scroll-bar-mode) (scroll-bar-mode -1))
(line-number-mode 1)
(column-number-mode 0)
;; A bigger default font helps GIF readability.
(when (display-graphic-p)
  (set-face-attribute 'default nil :height 140))

;; If markdown-mode is available, use it -- the section-by-section
;; conversation reads better with markdown highlighting.
(when (require 'markdown-mode nil 'noerror)
  (add-to-list 'auto-mode-alist '("\\.md\\'" . markdown-mode)))

;; Helper for the puppeteer: drop point into a fresh paragraph slot
;; right after the user's previous text in `## user', before any
;; existing `## agent:...' header. The puppeteer then types the
;; message char-by-char and hits C-x C-s.
(defun cotype-demo-position-for-user ()
  "Position point on a fresh blank line at the end of `## user' content.
If the buffer doesn't yet contain `## user' (e.g., it was loaded
before the on-disk template existed), revert it from disk first.
If even after that there's no `## user' header, abort with a clear
message rather than typing at point-min and corrupting the file."
  (interactive)
  (let ((find-user
         (lambda ()
           (goto-char (point-min))
           (re-search-forward "^## user[[:space:]]*$" nil t))))
    (unless (funcall find-user)
      ;; Buffer is stale relative to disk; pull the template in and retry.
      (when (and (buffer-file-name) (file-readable-p (buffer-file-name)))
        (revert-buffer 'ignore-auto 'no-confirm 'preserve-modes)
        (when (boundp 'cotype--ensure-auto-revert)
          (cotype--ensure-auto-revert)))
      (unless (funcall find-user)
        (user-error
         "cotype-demo-position-for-user: no `## user' header in buffer; \
refusing to type at point-min")))
    ;; We're now at the end of `## user'. Find the next section header
    ;; (or EOF), walk back over trailing blank lines, and land on a
    ;; fresh blank line right after the user's last non-blank content.
    (let ((next-section
           (save-excursion
             (if (re-search-forward "^## " nil t)
                 (line-beginning-position)
               (point-max)))))
      (goto-char next-section)
      (when (> (point) (point-min)) (forward-line -1))
      (while (and (> (point) (point-min))
                  (looking-at "^[[:space:]]*$"))
        (forward-line -1))
      (end-of-line)
      (insert "\n\n"))))
