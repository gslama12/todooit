# Vim engine for the notes editor

## Problem Statement

I write notes inside todooit, but the note editor only offers a handful of vim-like keys: moving, half pages, top and bottom, and one way into INSERT. Everything else needs INSERT mode, arrow keys, or desktop chords. I can't delete a word, change inside brackets, yank a line, or jump to a visible word the way my hands expect from LazyVim.

The note also doesn't store what I type. A typed `- ` is swapped for a bullet glyph on the spot, a heading becomes two lines, and emphasis becomes invisible characters. So I can never see or edit the real markup, and vim-style edits have no honest text to act on.

## Solution

The note editor behaves like LazyVim with my own key mapping. A note is stored as real markdown. The line under the cursor shows that raw markdown, and every other line is drawn rendered, so `- ` shows as a bullet until I stand on it.

NORMAL mode supports motions, operators with counts, text objects, VISUAL and V-LINE, registers, undo and redo, search, and a flash-style jump to any visible text. All keys are configurable, with my mapping as the default. The logic lives in a reusable engine, so the task description can adopt it later.

Existing notes are converted once at startup, after a backup of the database.

## User Stories

### Markdown notes

1. As a note writer, I want notes stored as real markdown, so that what I edit is the actual text.
2. As a note writer, I want the line under my cursor shown as raw markdown, so that I can see and edit its markup.
3. As a note writer, I want every other line drawn rendered, so that the note stays pleasant to read.
4. As a note writer, I want list items drawn with a bullet glyph by depth, so that nesting is visible at a glance.
5. As a note writer, I want numbered items to keep their current colours, so that lists look as they do today.
6. As a note writer, I want quotes drawn with a bar on every wrapped row, so that a long quote reads as one block.
7. As a note writer, I want a heading drawn as one underlined row across the window, so that it looks close to today's without an extra stored line.
8. As a note writer, I want all heading levels drawn in one style, so that the note keeps its simple look.
9. As a note writer, I want `---` drawn as a rule across the window, so that separators look like separators.
10. As a note writer, I want `*x*` and `**x**` drawn as emphasis with the marks hidden, so that both spellings work.
11. As a note writer, I want a link drawn as its name until I stand on that line, so that long URLs stay out of my way but remain editable.
12. As a note writer, I want all selected lines raw while in VISUAL, so that I can see exactly what I'm about to yank or delete.
13. As a note writer, I want the cursor line raw in INSERT too, with the rest of the note still rendered, so that only the line I'm on changes.
14. As a note writer, I want `enter` to continue a list and to exit it on an empty item, so that writing lists stays quick.
15. As a note writer, I want `tab` and `shift+tab` to nest and un-nest a line, so that nesting stays one key.
16. As a note writer, I want numbered lists to renumber themselves after edits, so that I never fix numbers by hand.
17. As a note writer, I want `backspace` to delete plain characters inside markers and emphasis, so that editing visible markup behaves predictably.

### Migration

18. As a user with existing notes, I want them converted to markdown at startup, so that I don't have to do anything.
19. As a user with existing notes, I want the database backed up outside the repo before conversion, so that I can recover if something goes wrong.
20. As a user, I want the app to stop with an error if the backup fails, so that no note is converted without a backup.
21. As a user, I want the conversion to run only once, so that later startups aren't affected.
22. As a user, I want binned todos' notes and the pinned note converted too, so that nothing stays in the old format.
23. As a user, I want nesting normalised to one consistent indent during conversion, so that depth reads correctly afterwards.

### Search and copy outside the editor

24. As a user, I want the app's note search to work on the markdown text directly, so that results reflect what's stored.
25. As a user, I want a search result to open the note with the cursor on the match, so that I land where I expected.
26. As a user, I want copying a note from a task row to give me its markdown as it is, so that it pastes cleanly elsewhere.

### Modes

27. As a note writer, I want a note to always open in NORMAL, even when empty, so that the keyboard always starts in the same state.
28. As a note writer, I want the mode chip to show NORMAL, INSERT, VISUAL, V-LINE or FLASH, so that I always know what my keys will do.
29. As a note writer, I want the hint line built from my configured keys, so that it's never wrong about them.
30. As a note writer, I want partial commands like `2d` shown beside the mode chip, so that I can see what's pending.
31. As a note writer, I want `escape` to cancel a pending operator, VISUAL, the search prompt or flash first, so that I don't close the note by accident.
32. As a note writer, I want the next `escape` to clear search highlights, so that I can dismiss them as in LazyVim.
33. As a note writer, I want `escape` from plain NORMAL to close the note, so that leaving stays one key.
34. As a note writer, I want the cursor kept on the last character in NORMAL and VISUAL, so that it behaves like vim.
35. As a note writer, I want 4 lines of context kept around the cursor, so that I can see what's next.
36. As a pinned-note user, I want the same engine there, so that I only learn one editor.

### Horizontal motions

37. As a vim user, I want `j` and `ö` to move left and right, so that my home row works.
38. As a vim user, I want `=` to go to the first non-blank character and `_` to the last character, so that line ends are one key away.
39. As a vim user, I want `w`, `b` and `e` to move by word, so that I can cross text quickly.
40. As a German-writing user, I want umlauts counted as word characters, so that `für` is one word.
41. As a vim user, I want `f`, `F`, `t` and `T` to jump to or just before a character, so that I can reach a spot on the line.
42. As a vim user, I want `h` to repeat the last character jump, so that I can step through occurrences.
43. As a vim user, I want `ü` and `ä` to go to the first non-blank of the line above and below, so that I can move line to line with no extra keys.

### Vertical motions

44. As a vim user, I want `k` and `l` to move up and down by screen row without a count, so that wrapped lines behave as in LazyVim.
45. As a vim user, I want `k` and `l` with a count to move by real line, so that counts stay predictable.
46. As a vim user, I want `C-u` and `C-d` to move half a page, so that I can scan long notes.
47. As a vim user, I want `gg` and `G` to go to the top and bottom, so that I can reach either end.
48. As a vim user, I want `{` and `}` to move by paragraph, so that I can move through sections.
49. As a vim user, I want `zz` to centre the view on the cursor, so that I can see the text around it.

### Entering INSERT and editing

50. As a vim user, I want `i` and `a` to insert before and after the cursor, so that I can start typing where I want.
51. As a user of my mapping, I want `A` to insert at line start and `I` at line end, so that the keys match my own muscle memory.
52. As a vim user, I want `o` and `O` to open a line below and above, carrying the list prefix, so that lists continue naturally.
53. As a vim user, I want `C` to change to the end of the line, so that I can rewrite a line's tail.
54. As a vim user, I want `cc` to change the line while keeping its indent and marker, so that a list item stays a list item.
55. As a vim user, I want `r` to replace one character, so that small typos cost one key.
56. As a vim user, I want `gi` to go back to my last insert position until the window closes, so that I can resume typing.
57. As a vim user, I want `dd` to delete a line and renumber its list, so that lists stay correct.
58. As a vim user, I want `D` to delete to the end of the line and `x` to delete one character, so that small deletions are quick.

### Operators, counts and text objects

59. As a vim user, I want `[count] operator [count] motion` with `d`, `c`, `y`, `>` and `<`, so that I can combine keys rather than memorise commands.
60. As a vim user, I want counts to multiply, so that `2d3w` deletes 6 words.
61. As a vim user, I want `>>` and `<<` to nest a line, so that I can indent from NORMAL.
62. As a vim user, I want one indent level to be 2 spaces, with quoted lines nesting after their `> `, so that indent matches the rest of the note.
63. As a vim user, I want `iw` and `aw` to behave as in default vim, so that `daw` doesn't join neighbouring words.
64. As a vim user, I want `iW`, `aW` and `i<space>` to select a run of non-whitespace, so that I can grab tokens.
65. As a vim user, I want `ip` and `ap` to select a paragraph, so that I can act on a block.
66. As a vim user, I want `i` and `a` with brackets and quotes, so that `ci"` and `di{` work.
67. As a vim user, I want those objects to use the next pair when I'm not inside one, so that `yi[` works from before the brackets.
68. As a vim user, I want an invalid key to cancel a pending command silently, so that mistakes are harmless.
69. As a vim user, I want no timeout on pending keys, so that I can pause mid-command.

### Yank, paste and undo

70. As a vim user, I want `yy` and `y` with motions and selections to yank text, so that I can reuse it.
71. As a vim user, I want `p` and `P` to paste after and before, respecting whether the yank was a whole line, so that `yyp` duplicates a line.
72. As a vim user, I want a yank in one note to paste in another, so that I can move text between notes.
73. As a user, I want `y` to also reach the system clipboard, so that I can paste into other apps.
74. As a user, I want `d`, `c` and `x` to leave the system clipboard alone, so that deleting doesn't overwrite what I copied elsewhere.
75. As a user, I want `p` to paste what I copied elsewhere if the system clipboard has changed since my last yank, so that pasting from a browser just works.
76. As a user, I want `p` to always paste text and `ctrl+v` to keep attaching files, so that the two don't get mixed up.
77. As a vim user, I want `u` and `C-r` to undo and redo, so that I can step through my changes.
78. As a vim user, I want each NORMAL command to be one undo step and a whole INSERT session to be one step, so that `u` matches what I did.
79. As a vim user, I want up to 1000 undo steps, so that I can go back a long way.

### VISUAL and V-LINE

80. As a vim user, I want `v` and `V` to select by character and by line, so that I can see a range before acting on it.
81. As a vim user, I want motions and text objects to extend the selection, so that `v_` and `vi{` work.
82. As a vim user, I want `o` in VISUAL to move to the other end, so that I can adjust either side.
83. As a vim user, I want `y`, `d`, `c`, `>`, `<` and `x` to act on the selection, so that the selection is useful.
84. As a vim user, I want `p` in VISUAL to replace the selection, so that it behaves as in vim.
85. As a vim user, I want indenting a selection to return to NORMAL, so that the mode is predictable.
86. As a user, I want shift or mouse selection in NORMAL to enter VISUAL, so that there's only one kind of selection.

### Search

87. As a vim user, I want `?` to search forward with the prompt in the hint line, so that I can find text.
88. As a vim user, I want matches highlighted and scrolled to as I type, so that I see results straight away.
89. As a vim user, I want `escape` during search to put the cursor back, so that I can abandon a search safely.
90. As a user, I want search to be plain text with smartcase, so that I don't have to think about patterns.
91. As a vim user, I want `n` to always go forward and `N` always backward, wrapping around and telling me, so that direction is never a surprise.
92. As a vim user, I want `*` to search the word under the cursor, whole word and ignoring case, so that I can find other uses.
93. As a vim user, I want my last search to last for the app session, so that `n` still works in another note.
94. As a vim user, I want `cgn`, `dgn`, `ygn` and `vgn` to act on the next match, so that I can edit matches one at a time.

### Flash jump

95. As a LazyVim user, I want `s` to narrow visible text as I type and label the matches, so that I can jump anywhere on screen in a few keys.
96. As a LazyVim user, I want labels placed after matches with closer ones first, so that the nearest targets are easiest.
97. As a LazyVim user, I want labels never to clash with a character that could continue my search, so that typing stays unambiguous.
98. As a LazyVim user, I want `enter` to jump to the first match and `escape` to cancel, so that I can finish without a label.
99. As a LazyVim user, I want a single match to wait for confirmation, so that the cursor never moves unexpectedly.
100. As a LazyVim user, I want `s` to work after operators and in VISUAL, so that `ds` and `vs` work.
101. As a note writer, I want flash to match links by their visible name, so that it searches what I can see.
102. As a user, I want the flash alphabet to be its own setting, so that it can differ from the task pane's.

### Configuration and moved keys

103. As a config author, I want every vim key configurable from the config file, so that the mapping is mine.
104. As a config author, I want my spec's mapping as the default, visible in the default config, so that I can read and change it.
105. As a vim-layout user, I want the QWERTZ and QWERTY templates to have more standard vim mappings, so that I can opt into familiar keys.
106. As a note writer, I want `gx` to open the link under the cursor, so that links stay reachable now `o` opens a line.
107. As a note writer, I want `gf` to open the attachment strip, so that files stay reachable now `f` is a jump.
108. As a note writer, I want `ctrl+u` and `ctrl+d` to clear the line and the note in INSERT, so that those shortcuts aren't lost.
109. As a user, I want `ctrl+c`, `ctrl+x`, `ctrl+v`, `ctrl+a` and shift-selection to keep working, so that desktop habits still work.
110. As a user, I want the attachment strip's keys unchanged, so that files behave as they do today.

### App-wide undo

111. As a user, I want `u` and `C-r` to be undo and redo in the task panes too, so that undo means one thing everywhere.
112. As a user, I want Bin restore on `R`, so that it survives `u` becoming undo.
113. As a user, I want `ctrl+z` and `ctrl+y` removed from the whole app, so that there's one set of undo keys.
114. As a note writer, I want those removed keys to do nothing in a note, so that they can't reach the panes behind it.

## Implementation Decisions

### Modules

- **Vim engine (new package):** a pure package with no Textual imports. It takes key strings and acts on a small buffer interface. It owns modes, key grammar, counts, motions, operators, text objects, registers, search state and flash state.
- **Buffer interface (new):** what the engine needs from any text host: lines, cursor, selection, replacing a range, grouping undo steps, and viewport size and scrolling. Commands that only make sense on multiple lines can be switched off, so a later single-line host can reuse the engine.
- **Note adapter (existing vim layer, reduced):** implements the buffer interface on the note editor and passes keys to the engine. List continuation, nesting and renumbering stay here. It stops holding key logic.
- **Vim keymap config (new API):** `api.vim.keys`, with `set` and `remap` in the style of the existing `api.keys`. Commands are named by enums such as a motion enum and a command enum. Default bindings are set in the default config, which is the source of truth.
- **Note display layer (changed):** what a line draws as depends on whether the cursor or a selection is on it. Typed-markup conversion goes. One generic "overlay spans" hook is added for search highlights and flash labels, and it knows nothing about vim.
- **Editor host interface (extended):** gains what the search prompt and pending-keys display need.
- **Note window (small change):** hints built from configured keys, new mode chips.
- **Database manager (changed):** runs the migration from its existing upgrade path on connect.
- **Note markdown translation (reduced):** shrinks to what a paste still needs.
- **Note search and note copy (changed):** work with stored markdown directly.
- **Default config and layout templates (changed):** vim keymap added, pane undo keys changed, restore moved.

### Stored format

- Notes are real markdown: `- `, `1. `, `> `, `# `, `---`, `*x*` or `**x**`, `[name](url)`.
- The engine only ever sees raw text, because the cursor line is always raw. No column conversion exists between engine and storage.

### Rendering

- Raw lines: the cursor line in NORMAL and INSERT, plus all selected lines in VISUAL and V-LINE.
- A heading is one row underlined across the window, because a drawn row that isn't in the document would break row mapping.
- No new markup is added. All heading levels share one style.
- Line height changing as the cursor enters a line is accepted.

### Migration

- One way, at startup, guarded by a marker in the database.
- The database is copied to a `backups` folder in its own data directory before anything changes. If the copy fails, the app stops with an error and nothing is migrated.
- Every todo note, including Bin rows, and the pinned note are converted using the existing conversion to markdown.
- Nesting is normalised to 2 spaces per level.
- Orphan emphasis marks are dropped. Undo history holds no note text on disk, so it needs nothing.

### Default keys

| Group | Keys |
|---|---|
| Move | `j` / `ö` left / right, `k` / `l` up / down |
| Line | `=` first non-blank, `_` last character, `ü` / `ä` first non-blank above / below |
| Word | `w`, `b`, `e` |
| Character jump | `f`, `F`, `t`, `T`; `h` repeats, `H` reverses |
| Page | `C-u`, `C-d`, `gg`, `G`, `{`, `}`, `zz` |
| Jump and search | `s`, `?`, `*`, `n`, `N`, `gn` |
| Insert | `i`, `a`, `A` (line start), `I` (line end), `o`, `O`, `gi` |
| Change and delete | `C`, `cc`, `r`, `dd`, `D`, `x` |
| Yank and paste | `yy`, `p`, `P` |
| Visual | `v`, `V`; `o` swaps ends inside VISUAL |
| Undo | `u`, `C-r` |
| Indent | `>>`, `<<` |
| Moved from old keys | `gx` link, `gf` attachment strip |
| Operators | `d`, `c`, `y`, `>`, `<` |

- `0`, `$` and `/` are unbound by default. The note editor no longer follows the panes' direction keys. The strip, calendar and help still do.
- Layout templates: `hjkl`, `0` or `^` and `$`, `I` / `A` at start / end, `/` to search. Repeat is `ö` on QWERTZ and `;` on QWERTY. QWERTY uses `-` / `+` for the line above and below.

### Grammar

- `[count] operator [count] motion | text-object`, with counts multiplying.
- No timeout on pending keys. An invalid key cancels silently.
- Motions: all of the above, including `f F t T`, `s` and `gn`. Words are letters, digits and `_`, Unicode included.
- Text objects: `iw aw` as in default vim, `iW aW i<space>`, `ip ap`, and `i` / `a` with `( ) [ ] { } < > " ' `` ` ``.
- When outside a pair, the next occurrence is used: through the whole note for brackets, within the line for quotes.

### `escape` order

Cancel pending operator, VISUAL, search prompt or flash; then clear search highlights; then close the note. From INSERT it goes to NORMAL.

### Registers

One internal register with text and a linewise flag, for the app session. `y` also copies to the system clipboard. `d`, `c`, `x` don't. `p` uses the register unless the system clipboard changed since the last yank, in which case it uses the existing paste path.

### Undo

- Each NORMAL command is one step and a whole INSERT session is one step, up to 1000.
- The note editor's built-in time and size batching must not split steps.
- INSERT has no undo key.

### Search and flash

- Search is plain text with smartcase, on raw text. `*` is whole word and ignores case. `n` is always forward and `N` always backward. Both wrap. The last search lasts for the app session, and highlights stay until `escape` or the next search.
- The note's flash mode is named `vim_flash` throughout (with `VimFlashMode`, `api.vars.vim_flash_alphabet`, and a `FLASH` chip) and shares no code or settings with the task pane's flash mode.
- Its behaviour follows flash.nvim defaults: exact mode, smartcase, labels after matches, closer targets first, uppercase labels allowed, labels never continue the pattern, no autojump, `enter` jumps to the first match. It searches drawn visible text in the one note on screen.

### Delivery slices

| # | Slice | Depends on |
|---|---|---|
| 0 | Markdown storage, migration, cursor-line rendering, with old keys still working | none |
| 1 | Engine core: buffer, adapter, keymap API, always-open-NORMAL, chip and hints, `escape`, clamping, scrolloff, motions, counts, `gx`, `gf`, templates | 0 |
| 2 | Operators, text objects, insert and line commands | 1 |
| 3 | Registers, clipboard rules, paste, undo, removing `ctrl+z`/`ctrl+y` in notes | 2 |
| 4 | VISUAL and V-LINE | 2, 3 |
| 5 | Search and the `gn` family | 2, 4 |
| 6 | `vim_flash` | 2, 4 |
| 7 | App-wide undo keys and moving restore to `R` | none |

## Testing Decisions

### What makes a good test

Tests assert external behaviour only: given text and a cursor, pressing keys produces this text, cursor, mode and register. They don't reach into engine internals, parser states or private adapter methods. They wait on state, never the clock, and stay independent so they can run in any order.

### Seams

There are two, highest first.

1. **Engine seam (main):** feed key strings to the engine over an in-memory buffer, then assert on text, cursor, selection, mode and register. Nearly all motions, operators, counts, text objects, registers, undo grouping, search and flash logic are tested here, without Textual.
2. **Note window seam:** a real app driven by a pilot, opening a note and pressing keys. This covers what only exists on screen: raw versus rendered lines, overlays, chip and hints, `escape` closing the window, the system clipboard, undo keys not reaching the panes, Karabiner byte sequences, and a few end-to-end checks per slice.

### Prior art

- Core tests with no app: the existing core test directory, especially the links tests.
- Pilot tests: the existing note UI tests and their open-note helper, the keyboard layout tests, and the Karabiner tests.
- A new `vim` marker, with new test files registered in the feature table, as the meta test requires.

### Existing tests

- Slice 0 rewrites the note markdown tests and much of the note UI tests.
- Slice 1 updates tests pressing old keys.
- Slice 7 updates pane undo and restore tests.

### Not tested

The startup migration of old databases gets no automated tests, by the owner's decision. The backup is its safety net.

## Out of Scope

- `.` repeat. `cgn` works once, and you continue with `n` and `cgn`.
- `S` (flash.nvim's treesitter jump).
- `$` auto-indent operator.
- `W`, `B`, `E` motions.
- Search patterns and search history.
- Named registers.
- New markup such as code blocks or checkboxes.
- The task description adapter, though the engine is designed for it.
- Docs and screenshots, which come in a later stage and go stale until then.
- Adding note keys to the help screen.

## Further Notes

### Check during implementation

1. Rendering is the highest risk: the document has to depend on the cursor row and re-wrap as it moves. Check that the view doesn't jump when a line above the viewport changes height.
2. Screen-row motion and mouse clicks must map correctly between rendered and raw lines.
3. Search highlights and flash labels must land correctly on rendered lines.
4. flash.nvim's README doesn't document three things: whether an operator includes the target, what happens with more matches than labels, and how labels are chosen. Read its source.

### Not explicitly confirmed by the owner

- `H` as reverse repeat was proposed and not explicitly confirmed.
- These Q24 items were accepted by silence: VISUAL `x` and `p`, pending keys beside the chip, `gi` lasting until the window closes, and the backup location.
- The exact layout-template mapping is a proposal.

### Sequencing

Slice 0 should be tried in the running app before the engine is built on it. Slice 7 can ship on its own, but until it does the panes keep `ctrl+z` and `ctrl+y`.
