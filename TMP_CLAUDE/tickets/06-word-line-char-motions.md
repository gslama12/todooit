# 06: Word, line and character motions with counts

**What to build:** The horizontal motions from the spec work with counts, and pending keys are visible.

**Blocked by:** 05

**Status:** ready-for-agent

- [ ] `w`, `b` and `e` move by word, where words are letters, digits and `_`, with umlauts counted as word characters
- [ ] `=` goes to the first non-blank character and `_` to the last character
- [ ] `ü` and `ä` go to the first non-blank of the line above and below
- [ ] `f`, `F`, `t` and `T` jump to or just before a character
- [ ] `h` repeats the last character jump and `H` reverses it
- [ ] Counts work on all of these, for example `3w`
- [ ] An invalid key cancels silently, and pending keys have no timeout
- [ ] Partial commands like `2f` show beside the mode chip
- [ ] `escape` cancels a pending command before it can close the note
- [ ] Engine-seam tests cover this behaviour: keys in, then text, cursor, selection, mode and register out
- [ ] Note-window pilot tests cover this behaviour for the pending-keys display
- [ ] Demo project seeded in this worktree's database, and the behaviour exercised in the running app
