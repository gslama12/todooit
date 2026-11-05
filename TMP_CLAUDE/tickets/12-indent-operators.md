# 12: Indent operators

**What to build:** Indenting and unindenting works from NORMAL as operators.

**Blocked by:** 03, 09

**Status:** ready-for-agent

- [ ] `>>` and `<<` nest and un-nest a line by one level of 2 spaces
- [ ] `>` and `<` work with motions and text objects, for example `>ip`
- [ ] Counts work, for example `3>>`
- [ ] A quoted line nests after its `> `
- [ ] Numbered lists renumber after indenting
- [ ] Engine-seam tests cover this behaviour: keys in, then text, cursor, selection, mode and register out
- [ ] Demo project seeded in this worktree's database, and the behaviour exercised in the running app
