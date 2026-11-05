# 11: Text objects

**What to build:** Text objects work with `d` and `c`, and also when the cursor is outside the pair.

**Blocked by:** 10

**Status:** ready-for-agent

- [ ] `iw` and `aw` behave as in default vim: `daw` on `bar` in `foo bar baz` gives `foo baz`
- [ ] `iW`, `aW` and `i<space>` act on a run of non-whitespace
- [ ] `ip` and `ap` act on a blank-line-separated paragraph, with `ap` including the trailing blank
- [ ] `i` and `a` work with `( ) [ ] { } < >`, across lines, and with `" ' `` ` ``, within a line
- [ ] `ci"`, `di{` and `da[` behave as in vim
- [ ] Outside a bracket pair, the next occurrence in the whole note is used
- [ ] Outside a quote pair, the next occurrence within the line is used
- [ ] Engine-seam tests cover this behaviour: keys in, then text, cursor, selection, mode and register out
- [ ] Demo project seeded in this worktree's database, and the behaviour exercised in the running app
