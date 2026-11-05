# 20: Vim layout templates

**What to build:** The QWERTZ and QWERTY templates offer more standard vim mappings. The jklö spec stays the default.

**Blocked by:** 08, 10, 16

**Status:** ready-for-agent

- [ ] Both templates set `h j k l` for movement in the note
- [ ] Both use `0` or `^` for line start and `$` for line end
- [ ] Both use `I` and `A` for insert at start and end
- [ ] Both use `/` to search forward
- [ ] Repeat is `ö` on QWERTZ and `;` on QWERTY
- [ ] QWERTY uses `-` and `+` for the line above and below, because it has no `ü` or `ä`
- [ ] Default config behaviour is unchanged when no template is used
- [ ] Keyboard-layout tests cover both templates
- [ ] Demo project seeded in this worktree's database, and the behaviour exercised in the running app
