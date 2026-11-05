# 02: Notes are written and drawn as markdown

**What to build:** Notes are now stored as real markdown. What's typed stays as typed, the cursor line shows it raw, and every other line is drawn rendered. Old keys still work. Land this together with tickets 03 and 04: until 04, existing notes show old glyphs as plain text.

**Blocked by:** 01

**Status:** ready-for-agent

- [ ] Typing `- `, `1. `, `> `, `# `, `---` or `*x*` stores exactly those characters, with no conversion at typing time
- [ ] Off the cursor line, `- ` and `* ` draw as a bullet glyph chosen by depth (`•`, `◦`, `▪`)
- [ ] Off the cursor line, numbered items keep their current colours, and quotes draw a bar on every wrapped row
- [ ] Off the cursor line, a heading of any level draws as one row in one style, underlined across the window width
- [ ] Off the cursor line, `---` draws as a rule across the window
- [ ] Off the cursor line, `*x*` and `**x**` draw as emphasis with the marks hidden
- [ ] The cursor line is raw in both NORMAL and INSERT, while the rest of the note stays rendered
- [ ] No new markup is added
- [ ] Note tests are rewritten for the new format where this ticket changes them
- [ ] Note-window pilot tests cover this behaviour
- [ ] Demo project seeded in this worktree's database, and the behaviour exercised in the running app
