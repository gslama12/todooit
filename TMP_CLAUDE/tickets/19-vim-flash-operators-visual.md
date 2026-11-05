# 19: `vim_flash` with operators and VISUAL

**What to build:** `s` works as a motion after operators and while selecting.

**Blocked by:** 09, 15, 18

**Status:** ready-for-agent

- [ ] The flash.nvim source has been read for whether an operator includes the target, and its behaviour is followed
- [ ] `ds`, `cs` and `ys` act from the cursor to the chosen target, in either direction
- [ ] `s` in VISUAL and V-LINE extends the selection
- [ ] `escape` cancels and leaves the pending operator or selection in its proper state
- [ ] Engine-seam tests cover this behaviour: keys in, then text, cursor, selection, mode and register out
- [ ] Demo project seeded in this worktree's database, and the behaviour exercised in the running app
