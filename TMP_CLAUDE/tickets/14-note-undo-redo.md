# 14: Undo and redo in notes

**What to build:** `u` and `C-r` step through changes the way vim groups them, replacing the note's old undo keys.

**Blocked by:** 10

**Status:** ready-for-agent

- [ ] `u` undoes and `C-r` redoes
- [ ] Each NORMAL command is one step
- [ ] A whole INSERT session is one step, however long it runs
- [ ] The editor's built-in time and size batching doesn't split steps
- [ ] Up to 1000 steps are kept
- [ ] `ctrl+z`, `ctrl+y` and `super+z` do nothing in a note, and don't reach the panes behind it
- [ ] Engine-seam tests cover this behaviour: keys in, then text, cursor, selection, mode and register out
- [ ] Note-window pilot tests cover this behaviour for the removed keys
- [ ] Demo project seeded in this worktree's database, and the behaviour exercised in the running app
