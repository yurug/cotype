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
# With fake-claude this finishes in <2 s; with real claude expect
# ~10-15 s for three concurrent calls.
Sleep 12000ms

# Round 2 (puppeteer T~12 s): user M-x's `stile-demo-add-spec` to
# insert a stricter spec line:
#     "Reject non-integer input with ValueError."
# code rewrites the body to validate; tests adds a try/except
# assertion; docs updates the docstring. ~10-15 s.
Sleep 15000ms

# Round 3 (puppeteer T~27 s): user adds
#     "Accept any iterable, not just a list."
# code switches to a manual-loop accumulator; tests adds an `iter(...)`
# assertion; docs becomes "Accepts any iterable of int". ~10-15 s.
Sleep 12000ms

# Linger on the final state.
Sleep 5000ms
