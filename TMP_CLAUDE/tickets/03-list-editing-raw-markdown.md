# 03: List editing on raw markdown

**What to build:** List conveniences work on raw markdown markers, and the backspace behaviour that existed only for invisible markup is gone.

**Blocked by:** 02

**Status:** ready-for-agent

- [ ] `enter` continues a list with its prefix, and exits on an empty item as it does today
- [ ] `enter` on an empty nested item steps out one level
- [ ] `tab` and `shift+tab` nest and un-nest by 2 spaces, with quoted lines nesting after their `> `
- [ ] Numbered lists renumber after edits
- [ ] `enter` no longer skips a heading's rule, because the rule line no longer exists
- [ ] `backspace` deletes plain characters inside markers and after emphasis
- [ ] Note tests are rewritten for this behaviour
- [ ] Note-window pilot tests cover this behaviour
- [ ] Demo project seeded in this worktree's database, and the behaviour exercised in the running app
