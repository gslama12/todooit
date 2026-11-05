# 07: Page motions and scrolloff

**What to build:** Vertical movement behaves as in LazyVim.

**Blocked by:** 05

**Status:** ready-for-agent

- [ ] `C-u` and `C-d` move half a page in NORMAL
- [ ] `gg` and `G` go to the top and bottom of the note
- [ ] `{` and `}` move by paragraph, separated by blank lines
- [ ] `zz` centres the view on the cursor
- [ ] `k` and `l` move by screen row without a count, and by real line with one
- [ ] 4 lines of context are kept above and below the cursor, wherever the note allows it
- [ ] Engine-seam tests cover this behaviour: keys in, then text, cursor, selection, mode and register out
- [ ] Note-window pilot tests cover this behaviour for scrolling and scrolloff
- [ ] Demo project seeded in this worktree's database, and the behaviour exercised in the running app
