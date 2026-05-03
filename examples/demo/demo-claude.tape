# Multi-round Claude-driven demo: collaboratively design `sum_evens(xs)`.
# ~45 s visible.
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

Hide
Type "./demo-claude.sh"
Enter
Sleep 3000ms
Show

# Round 1: Emacs is up. The `code` agent reacts to the seeded `## spec`
# and writes the first implementation. `tests` and `docs` waited for the
# `## code` placeholder to fill in; once it does they cascade.
# Fake-claude: <2 s; real claude: ~10-15 s for three concurrent calls.
Sleep 12000ms

# Round 2 (puppeteer T~12 s): the `user` pane shows
#     ✎ typing in ## spec…
#     "Reject non-integer input with ValueError."
# while the puppeteer hits M-x stile-demo-position-for-spec and then
# pecks the bullet text char-by-char into the spec section of Emacs
# (~2-3 s of visible typing), then C-x C-s. `code` rewrites the body
# to validate; tests adds a try/except assertion; docs updates
# the docstring. ~12-18 s total.
Sleep 18000ms

# Round 3 (puppeteer T~27 s): user types
#     "Accept any iterable, not just a list."
# `code` switches to a manual-loop accumulator; tests adds an
# `iter(...)` assertion; docs becomes "Accepts any iterable of int".
Sleep 14000ms

# Linger on the final state.
Sleep 5000ms
