# stile demo -- 4 panes, real concurrent agent processes editing the
# SAME task.md. Top pane: live editor view of the file. Bottom row:
# three bg-agent.py processes that each call `stile open` + `stile save`
# in parallel; the first save lands `direct` and the next two are 3-way
# merged because their bases went stale.
#
# Render:
#   cd examples/twitter-demo
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
# Launch the demo: this kills any prior session, re-seeds /tmp/stile-twitter-demo,
# starts the 4-pane tmux layout, attaches.  Each agent shows "open  (base ...)"
# very quickly, then waits at a barrier until all three have captured the same
# base, then saves with a small jitter so the cascade is visible.
Hide
Type "./demo.sh"
Enter
Sleep 2500ms
Show

# === Visible: real concurrent agents save into the same file ===
# Phase: opens land (~0.5s), barrier passes, saves cascade.
Sleep 5000ms

# Linger on the final state so the four populated sections register.
Sleep 5000ms

# === Off-screen cleanup: detach from tmux + kill the session ===
Hide
Ctrl+B
Type "d"
Sleep 300ms
Type "tmux kill-session -t stile-tmux-demo 2>/dev/null"
Enter
