# Single-pane "narrated" demo: one user + three agents, scripted output
# of `direct, merged, merged`. Useful as a typed transcript; the multi-pane
# version in `demo.tape` is the one the project advertises.
#
# Run: cd examples/demo && vhs simple-demo.tape

Output simple-demo.gif
Output simple-demo.mp4

Set Shell "bash"
Set FontSize 18
Set Width 1100
Set Height 720
Set Theme "Dracula"
Set TypingSpeed 28ms
Set PlaybackSpeed 1.0

# === Off-screen setup ===
# Seed the working dir, alias `agents` so the visible command is short.
Hide
Type "STILE_DEMO=$(pwd)"
Enter
Type "./setup.sh /tmp/stile-demo > /dev/null"
Enter
Type "alias agents='python3 $STILE_DEMO/orchestrate.py task.md'"
Enter
Type "cd /tmp/stile-demo"
Enter
Type "clear"
Enter
Show

# === Visible ===

Type "cat task.md"
Enter
Sleep 2500ms

Type "# 1 user (Emacs) + 3 agents on the same shared file"
Enter
Sleep 1000ms

Type "agents"
Enter
Sleep 2000ms

Type "cat task.md"
Enter
Sleep 5000ms

Type "# four writers, no lost edits."
Enter
Sleep 1500ms
