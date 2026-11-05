# 21: App-wide undo keys

**What to build:** Undo means one thing everywhere: the task panes use `u` and `C-r`. This is the one change outside the note feature.

**Blocked by:** None (can start immediately)

**Status:** ready-for-agent

- [ ] `u` undoes and `C-r` redoes in the task panes
- [ ] Bin restore moves from `u` to `R`
- [ ] `ctrl+z` and `ctrl+y` are removed from the whole app
- [ ] Existing undo and restore tests are updated, including pane, calendar and refresh-signal tests pressing the old keys
- [ ] Docs stay as they are until the later docs stage
- [ ] Pilot tests cover undo, redo and restore on the new keys
- [ ] Demo project seeded in this worktree's database, and the behaviour exercised in the running app
