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

# Round 1: Emacs is up. Engineer reacts to the seeded ## requirements;
# tester and marketer wait for engineer, then react to the new ## engineer
# section. With fake-claude this cascades in <2 s; with real claude
# expect ~10-15 s for three concurrent calls.
Sleep 12000ms

# Round 2 (T~12 s on the puppeteer's clock): the puppeteer M-x's the
# `stile-demo-add-requirement` helper to insert
#   "must survive a 5-year-old throwing it at a wall"
# under ## requirements. Engineer regenerates ## engineer with an
# impact-rated design; tester adds a wall-impact test; marketer
# reaches for a tagline. ~10-15 s.
Sleep 15000ms

# Round 3 (T~27 s on the puppeteer's clock): the puppeteer adds
#   "BOM under $5 (no NASA contracts)"
# Engineer downgrades to cardboard + tape; tester drops the
# wall-impact test (out of budget); marketer goes burrito.
Sleep 12000ms

# Linger on the final state.
Sleep 5000ms
