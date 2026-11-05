# 10: Insert and change commands

**What to build:** All the ways into INSERT from the spec work, along with the `c` operator.

**Blocked by:** 09

**Status:** ready-for-agent

- [ ] `i` and `a` insert before and after the cursor
- [ ] `A` inserts at the first non-blank and `I` at the end of the line, swapped on purpose
- [ ] `o` and `O` open a line below and above, carrying the list prefix
- [ ] `c` works with motions, and `cw` acts from the cursor as in vim
- [ ] `C` changes to the end of the line
- [ ] `cc` keeps indent and marker, so `- foo` becomes `- ` with the cursor after it
- [ ] `r` replaces one character
- [ ] `gi` returns to the last insert position, remembered until the window closes
- [ ] Engine-seam tests cover this behaviour: keys in, then text, cursor, selection, mode and register out
- [ ] Note-window pilot tests cover this behaviour for entering INSERT and typing
- [ ] Demo project seeded in this worktree's database, and the behaviour exercised in the running app
