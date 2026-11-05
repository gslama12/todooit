# 15: VISUAL and V-LINE

**What to build:** Selecting by character and by line works, and operators act on the selection.

**Blocked by:** 11, 12, 13

**Status:** ready-for-agent

- [ ] `v` and `V` enter VISUAL and V-LINE, shown on the mode chip
- [ ] All selected lines draw raw
- [ ] Motions and text objects extend the selection, for example `v_` and `vi{`
- [ ] `viW` and `vi<space>` select a run of non-whitespace
- [ ] `o` moves the cursor to the other end of the selection
- [ ] `y`, `d`, `c`, `>`, `<` and `x` act on the selection, and indenting returns to NORMAL
- [ ] `p` replaces the selection
- [ ] The cursor is clamped to the last character
- [ ] Shift or mouse selection from NORMAL enters VISUAL
- [ ] `escape` cancels VISUAL before it can close the note
- [ ] Engine-seam tests cover this behaviour: keys in, then text, cursor, selection, mode and register out
- [ ] Note-window pilot tests cover this behaviour for drawing and shift or mouse selection
- [ ] Demo project seeded in this worktree's database, and the behaviour exercised in the running app
