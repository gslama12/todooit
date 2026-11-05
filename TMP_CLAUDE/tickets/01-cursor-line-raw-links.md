# 01: Cursor line shows raw links

**What to build:** A folded link expands to its full `[name](url)` when the cursor stands on its line, and folds again when the cursor leaves. This is the first step toward 'the cursor line is raw', proving the riskiest part of the rendering before storage changes. Storage and all keys are unchanged.

**Blocked by:** None (can start immediately)

**Status:** done

- [x] Standing on a line with a link shows the full markdown link, and cursor columns on that line are stored columns
- [x] Leaving the line folds the link back to its name
- [x] A line that changes height as the cursor enters or leaves re-wraps correctly, including its hanging indent
- [x] The view doesn't jump when a line above the viewport changes height
- [x] Up and down movement by screen row lands sensibly when crossing between raw and rendered lines
- [x] A mouse click on a rendered line puts the cursor on the character that was clicked
- [x] Editing on the cursor line edits the stored text directly, with no link-widening behaviour needed
- [x] Note-window pilot tests cover this behaviour
- [x] Demo project seeded in this worktree's database, and the behaviour exercised in the running app
