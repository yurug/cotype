# stile crêpe-stand brainstorming demo -- 3 panes, real Claude calls.
#
# Top pane: Emacs viewing brainstorm.md (stile-mode + auto-revert).
# Bottom-left: puppeteer that types in the `## user' section across
# three rounds (challenge → focusing question → "we're done").
# Bottom-right: headless-agents.sh running cook, logistics, ux-designer,
# note-taker -- each owns its own `## agent:<role>' section.
#
# The recording is ~95 s end-to-end: 4 s for Emacs to come up, then
# three rounds of brainstorming with ~28 s between user messages, plus
# a final lingering shot of the populated file.
#
# Render: cd examples/demo-crepe && vhs demo.tape
# Outputs: demo.gif, demo.mp4

Output demo.gif
Output demo.mp4

Set Shell "bash"
Set FontSize 16
Set Width 1600
Set Height 1000
Set Theme "Dracula"
Set TypingSpeed 30ms
Set Padding 12

# === Off-screen launch: spin up the tmux session and attach. The
# demo.sh script kills any prior session, re-seeds the workspace, and
# attaches us to the live tmux. ===
Hide
Type "./demo.sh"
Enter
Sleep 3000ms
Show

# === Visible from here ===
# t≈0: Emacs is up, agents and puppeteer launching.
# t≈4s: puppeteer types round-1 question, saves.
# t≈10-30s: cook → logistics → ux → note-taker each post their first
#           replies (Sonnet ~2-4 s/turn, STAGGER=3 between agents).
# t≈32s: puppeteer types round-2 (focusing) question.
# t≈40-60s: round-2 replies cascade.
# t≈62s: puppeteer types "Perfect — we have a plan. Thanks all!"
# t≈65-75s: agents see no new question and idle (no-change skip).
# t≈75-90s: linger on the final populated file.
Sleep 92000ms

# === Off-screen cleanup: detach + kill the tmux session ===
Hide
Ctrl+B
Type "d"
Sleep 300ms
Type "tmux kill-session -t stile-crepe-demo 2>/dev/null"
Enter
