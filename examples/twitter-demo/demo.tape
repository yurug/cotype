# stile demo -- 1 user (Emacs) + 3 agents on the SAME task.md.
# Run from this directory:
#   cd examples/twitter-demo
#   vhs demo.tape
# Output: demo.gif (and demo.mp4) ready to upload to Twitter/X.

Output demo.gif
Output demo.mp4

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
Type "./setup.sh /tmp/stile-twitter-demo > /dev/null"
Enter
Type "alias agents='python3 $STILE_DEMO/orchestrate.py task.md'"
Enter
Type "cd /tmp/stile-twitter-demo"
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
