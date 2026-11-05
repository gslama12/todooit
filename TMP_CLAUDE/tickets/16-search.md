# 16: Search

**What to build:** `?` and `*` search the note as in LazyVim, using plain text only.

**Blocked by:** 06

**Status:** ready-for-agent

- [ ] `?` opens a prompt in the hint line and searches forward
- [ ] Matching is plain text and ignores case unless the search has a capital
- [ ] The first match is highlighted and scrolled to while typing
- [ ] `enter` confirms, and `escape` cancels and restores the cursor
- [ ] Matching uses raw text, including a link's hidden URL, and that line goes raw when the cursor lands there
- [ ] `n` always goes forward and `N` always backward; both wrap and say so in the hint line
- [ ] With no search yet, `n` and `N` report that
- [ ] `*` searches the word under the cursor, as a whole word, ignoring case
- [ ] Highlights stay until the next search or `escape`, and that `escape` doesn't close the note
- [ ] The last search lasts for the app session, and there's no history
- [ ] A generic overlay-spans hook on the note view draws highlights correctly on rendered lines, and knows nothing about vim
- [ ] Engine-seam tests cover this behaviour: keys in, then text, cursor, selection, mode and register out
- [ ] Note-window pilot tests cover this behaviour for the prompt and highlights
- [ ] Demo project seeded in this worktree's database, and the behaviour exercised in the running app
