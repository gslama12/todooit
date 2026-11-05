# 04: Existing notes become markdown

**What to build:** Existing notes are converted once at startup after a backup, and everything else that reads note text uses markdown directly. The migration is one way.

**Blocked by:** 02

**Status:** ready-for-agent

- [ ] On first startup, the database is copied to a `backups` folder in its own data directory, outside the repo
- [ ] If the copy fails, the app stops with an error and nothing is migrated
- [ ] Every todo note, Bin rows included, and the pinned note are converted
- [ ] Nesting is normalised to 2 spaces per level, including nested numbered items
- [ ] A marker in the database stops the migration running again
- [ ] Note search matches and shows the markdown text directly
- [ ] A search result opens the note with the cursor on the match
- [ ] Copying a note from a task row gives its markdown as it is
- [ ] Pasting still works, with the markdown translation reduced to what a paste needs
- [ ] No automated tests are written for migrating old databases, by the owner's decision
- [ ] The migration is checked by hand against a copy of a real database, and never against the live one
- [ ] Note-window pilot tests cover this behaviour for search, copy and paste
- [ ] Demo project seeded in this worktree's database, and the behaviour exercised in the running app
