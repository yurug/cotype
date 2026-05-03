# stile demo -- 4 panes, real concurrent agent processes editing the
# SAME task.md. Top pane: live editor view of the file. Bottom row:
# three bg-agent.py processes that each call `stile open` + `stile save`
# in parallel; the first save lands `direct` and the next two are 3-way
# merged because their bases went stale.
#
# Render:
#   cd examples/demo
#   vhs demo.tape
# Outputs: demo.gif, demo.mp4

Output demo.gif
Output demo.mp4

Set Shell "bash"
Set FontSize 14
Set Width 1400
Set Height 900
Set Theme "Dracula"
Set TypingSpeed 30ms
Set Padding 10

# === Off-screen ===
# Launch the demo: kills any prior session, re-seeds /tmp/stile-demo,
# creates the 4-pane tmux layout, sends Emacs to the top pane, sends the
# three agent processes to the bottom panes (each with a 2 s pre-open
# delay so Emacs has time to come up first), and attaches.
Hide
Type "./demo.sh"
Enter
Sleep 2500ms
Show

# === Visible from here ===
# Emacs finishes its startup (-Q + our demo-init.el), opens task.md,
# auto-enables stile-mode, captures its base. ~1 s.
# Then the three agents wake from their START_DELAY and the cascade
# fires: reviewer direct, linter merged, tester merged. Emacs's
# auto-revert (file-notify) reloads the buffer after each save, so the
# top pane visibly grows section by section.
Sleep 6500ms

# Linger on the final populated buffer.
Sleep 4000ms

# === Off-screen cleanup: detach from tmux + kill the session ===
Hide
Ctrl+B
Type "d"
Sleep 300ms
Type "tmux kill-session -t stile-tmux-demo 2>/dev/null"
Enter
