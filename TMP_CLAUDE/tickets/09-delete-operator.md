# 09: Delete operator

**What to build:** The operator grammar exists, proven with delete: `[count] operator [count] motion`.

**Blocked by:** 06

**Status:** ready-for-agent

- [ ] `d` works with every available motion, for example `dw`, `de`, `db`, `dt,`, `d=` and `d_`
- [ ] Counts multiply, so `2d3w` deletes 6 words
- [ ] `dd`, including `3dd`, deletes whole lines
- [ ] `D` deletes to the end of the line and `x` deletes the character under the cursor
- [ ] Deleting from a numbered list renumbers it, and edits on a marker apply literally and then renumber
- [ ] `d_` includes the last character but not the line break
- [ ] `escape` cancels a pending operator
- [ ] Pending operators show beside the mode chip
- [ ] Engine-seam tests cover this behaviour: keys in, then text, cursor, selection, mode and register out
- [ ] Note-window pilot tests cover this behaviour for an end-to-end delete
- [ ] Demo project seeded in this worktree's database, and the behaviour exercised in the running app
