# Multi-round Claude-driven demo. ~50 s visible.
#
# Render:
#   cd examples/twitter-demo
#   vhs demo-claude.tape
# Outputs: demo-claude.gif, demo-claude.mp4

Output demo-claude.gif
Output demo-claude.mp4

Set Shell "bash"
Set FontSize 14
Set Width 1400
Set Height 900
Set Theme "Dracula"
Set TypingSpeed 30ms
Set Padding 10

# Off-screen launch
Hide
Type "./demo-claude.sh"
Enter
Sleep 3000ms
Show

# Round 1: Emacs is up, agents see the seeded ## user block, each calls
# `claude` and saves their response. ~10-18 s for three concurrent calls.
Sleep 18000ms

# Round 2: puppeteer (T~15 s on its own clock) types a follow-up and
# saves; agents respond again. ~15-20 s.
Sleep 20000ms

# Round 3: puppeteer wraps; agents may briefly respond.
Sleep 9000ms

# Linger on the final state
Sleep 4000ms
