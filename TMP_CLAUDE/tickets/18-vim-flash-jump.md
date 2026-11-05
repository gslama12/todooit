# 18: `vim_flash` jump

**What to build:** `s` jumps to any visible text with labels, following flash.nvim. This is named `vim_flash` throughout and shares no code or settings with the task pane's flash mode.

**Blocked by:** 16

**Status:** ready-for-agent

- [ ] The flash.nvim source has been read first for how labels are chosen and what happens with more matches than labels, and its behaviour is followed
- [ ] `s` shows the `FLASH` mode chip, and each typed character narrows matches on visible text as drawn
- [ ] A link matches on its visible name, not its URL
- [ ] Matching is exact with smartcase, within the one note on screen
- [ ] Labels go after matches, closer targets get labels first, and uppercase labels are allowed
- [ ] A label never continues the search text
- [ ] Pressing a label jumps, and `enter` jumps to the first match
- [ ] A single match doesn't jump by itself
- [ ] `escape` cancels, leaving the cursor where it was, without closing the note
- [ ] Labels come from `api.vars.vim_flash_alphabet`, with the same default letters as the pane's but as a separate setting
- [ ] Labels draw correctly on rendered lines through the overlay hook
- [ ] Engine-seam tests cover this behaviour: keys in, then text, cursor, selection, mode and register out
- [ ] Note-window pilot tests cover this behaviour for drawing
- [ ] Demo project seeded in this worktree's database, and the behaviour exercised in the running app
