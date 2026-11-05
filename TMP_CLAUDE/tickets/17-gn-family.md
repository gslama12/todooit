# 17: `gn` family

**What to build:** `gn` works as a motion, so matches can be edited one at a time. There's no `.` repeat: to continue, press `n` and type `cgn` again.

**Blocked by:** 10, 15, 16

**Status:** ready-for-agent

- [ ] `cgn` changes the next match and enters INSERT
- [ ] `dgn` deletes it and `ygn` yanks it
- [ ] `vgn` selects it
- [ ] With no search yet, it reports that and changes nothing
- [ ] Engine-seam tests cover this behaviour: keys in, then text, cursor, selection, mode and register out
- [ ] Demo project seeded in this worktree's database, and the behaviour exercised in the running app
