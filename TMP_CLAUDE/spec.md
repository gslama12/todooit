# Vim engine for the notes editor: agreed spec

Worktree and branch: `feat-vim-module`, from `dev` (bd5559be).
Decision history: `TMP_CLAUDE/design-log.md`.

Reading order: sections 1-5 are the behaviour, section 6 cuts it into slices for
tickets, section 7 lists what's out of scope, and section 8 lists what's still
uncertain and has to be checked during implementation.

---

## 1. Architecture

- **`todooit/vim_engine/`**: a pure package with no Textual imports. It takes key
  strings and acts on a small `Buffer` protocol (lines, cursor, selection,
  replace, undo group, viewport).
- **`todooit/ui/screens/note/vim/`**: a thin adapter from `NoteEditor` to the engine.
- The engine sees raw markdown only and never converts columns. The cursor line is
  always drawn raw, so engine columns are stored columns.
- `read_only` remains the difference between NORMAL and INSERT. `TextArea.edit` has
  no read_only check, so engine edits work in NORMAL. VISUAL and flash stay
  read_only too.
- Line-only commands must be able to be switched off, so a later single-line
  adapter (the task description) can reuse the engine. That adapter isn't built
  here.
- Edits outside `vim/` are allowed where the feature needs them. Other parts of the
  app stay untouched.

### Naming

The note's jump mode is **`vim_flash`**: `vim_engine/vim_flash.py`, `VimFlashMode`,
`api.vars.vim_flash_alphabet`, mode chip `FLASH`. It shares no code or settings
with the task pane's `FlashJump`, `flash_labels`, `FLASH_ALPHABET` or
`api.vars.flash_alphabet`. Tests use a new `vim` marker, not `flash`.

---

## 2. Storage and rendering

### Stored format

Notes are stored as real markdown: `- foo`, `1. foo`, `> q`, `# Title`, `---`,
`**x**`, `[name](url)`. All edits act on this text.

### What is drawn

| Line state | Drawn as |
|---|---|
| Cursor line, NORMAL or INSERT | Raw markdown |
| All selected lines, VISUAL / V-LINE | Raw markdown |
| Every other line | Rendered, as below |

| Markdown | Rendered |
|---|---|
| `- x` / `* x` | Bullet glyph by depth (`•`, `◦`, `▪`) |
| `1. x` | Number, coloured as now |
| `> x` | Quote bar, wrapped rows keep the bar |
| `# x` (any level) | One heading style, one row, underlined across the window width |
| `---` | Rule across the window |
| `*x*`, `**x**` | Orange emphasis, marks hidden |
| `[name](url)`, long bare URL | Name only, underlined |

- No new markup: no code blocks or checkboxes.
- A line can change height when the cursor enters it. That is accepted.

### Migration (one way)

Runs at startup from the existing upgrade path in `api/manager.py`.

1. Skip if the database's migration marker is set.
2. Copy the database to `<data dir>/backups/` (for the live instance,
   `~/.local/share/todooit/backups/`). This is outside the repo.
3. If the copy fails, stop with an error and migrate nothing.
4. Convert every todo note, Bin rows included, and the pinned note with
   `to_markdown`.
5. Normalise nesting to 2 spaces per level. `to_markdown` gives nested numbers a
   3-space indent.
6. Set the marker.

Orphan emphasis marks are dropped by the conversion. Undo history stores no note
text on disk, so it needs no conversion. Older builds would show raw markdown, with
nothing lost.

### Other consumers

- `screens/search.py`: searches and displays the raw markdown. `drawn_column` and
  folding go.
- `NoteScreenBase.go_to`: column is used as stored, with no conversion.
- `trees/todos_tree.py` (`ctrl+n`): copies the note text verbatim.
- `disp/typed.py`: its conversions go.
- `disp/markdown.py`: shrinks to what a paste still needs.

### INSERT behaviour on raw text

| Behaviour | Result |
|---|---|
| `enter` continues a list, exits on an empty item | Keep |
| `tab` / `shift+tab` nesting | Keep |
| List renumbering | Keep |
| `enter` at a heading's end skipping its rule | Remove |
| `backspace` in a marker dedents | Remove, deletes characters |
| `backspace` after emphasis removes it | Remove, deletes characters |

---

## 3. Keys

All are configurable. The defaults below are the initial spec and are visible in
`todooit/utils/default_config.py`:

```python
api.vim.keys.set("j", VimMotion.LEFT)
api.vim.keys.set("dd", VimCommand.DELETE_LINE)
api.vim.keys.remap({"j": "h", "ö": "l"})
```

The note editor no longer follows `motion_keys()`. The attachment strip, calendar
and help screens still do. Note keys aren't added to the help screen.

### Motions

| Key | Action |
|---|---|
| `j` / `ö` | Left / right |
| `k` / `l` | Up / down. By screen row without a count, by real line with one |
| `=` | First non-blank of the line |
| `_` | Last character of the line. `d_` and `v_` include it, not the line break |
| `w` / `b` / `e` | Word forward / backward / end of word |
| `f` / `F` | Jump to character forward / backward |
| `t` / `T` | Jump just before character forward / backward |
| `h` | Repeat the last `f F t T` |
| `H` | Repeat it in reverse (proposed addition, not in the initial spec) |
| `ü` / `ä` | First non-blank of line above / below |
| `C-u` / `C-d` | Half page up / down |
| `gg` / `G` | Top / bottom of the note |
| `{` / `}` | Paragraph up / down |
| `s` | vim_flash |
| `n` / `N` | Next / previous match |
| `gn` | Next match, as a motion (`cgn`, `dgn`, `ygn`, `vgn`) |

Words are letters, digits and `_`, umlauts included. `cw` acts from the cursor, as
in vim.

### Commands

| Key | Action |
|---|---|
| `i` / `a` | Insert before / after the cursor |
| `A` / `I` | Insert at start (first non-blank) / end of line. Swapped on purpose |
| `o` / `O` | Open a line below / above, carrying the list prefix |
| `C` | Change to end of line |
| `cc` | Change line, keeping indent and marker (`- foo` becomes `- `) |
| `r` | Replace one character |
| `dd` | Delete line, renumber the list |
| `D` | Delete to end of line |
| `x` | Delete the character under the cursor |
| `yy` | Yank line |
| `p` / `P` | Paste after / before |
| `v` / `V` | VISUAL / V-LINE |
| `*` | Search for the word under the cursor |
| `?` | Search forward |
| `u` / `C-r` | Undo / redo |
| `gi` | Go to last insert position, until the window closes |
| `zz` | Centre the view on the cursor |
| `>>` / `<<` | Indent / unindent line |
| `gx` | Open the link under the cursor (was `o`) |
| `gf` | Hand the keyboard to the attachment strip (was `f`) |

### Operators and grammar

`[count] operator [count] motion | text-object`. Counts multiply: `2d3w` deletes
6 words.

- Operators: `d`, `c`, `y`, `>`, `<`.
- Motions: everything in the motions table, including `f F t T`, `s` and `gn`.
- Plain text edits on a marker (`x`, `dw`, `C`) apply literally, then the list is
  renumbered.
- There's no timeout on pending keys. An invalid key cancels silently.
- Pending keys such as `2d` show beside the mode chip.

`>` and `<`: one level is 2 spaces. A quoted line nests after its `> `. After a
visual selection they return to NORMAL.

### Text objects

| Object | Meaning |
|---|---|
| `iw` / `aw` | Inner word / word as in default vim: trailing whitespace, or leading if there's none |
| `iW` / `aW` | Run of non-whitespace |
| `i<space>` | Same as `iW` |
| `ip` / `ap` | Paragraph, blank-line separated; `ap` includes the trailing blank |
| `i` / `a` + `( ) [ ] { } < >` | Inside / around a pair |
| `i` / `a` + `" ' `` ` `` ` | Inside / around quotes |

When the cursor isn't inside a pair, the next occurrence is used: through the whole
note for brackets, within the line for quotes.

### VISUAL and V-LINE

- `v` and `V` use `TextArea` selection.
- Motions and text objects extend the selection. `s` extends it too.
- `o` moves the cursor to the other end.
- `y`, `d`, `c`, `>`, `<` act on the selection. `x` works like `d`, `p` replaces it.
- Shift or mouse selection from NORMAL enters VISUAL automatically.

### Kept keys

`ctrl+c`, `ctrl+x`, `ctrl+v`, `ctrl+a` and shift-selection keep working.
`ctrl+u` and `ctrl+d`, with their Cmd equivalents on Mac, are half page in NORMAL
and clear line / clear note (y/N) in INSERT.

### Removed from the note editor

`0` and `$` are unbound. Bare `u` and `d` no longer scroll, `f` no longer opens the
strip, and `o` no longer opens links. `/` is unbound.

### Vim layout templates

`config/qwertz_vim.py` and `config/qwerty_vim.py` get more default-vim keymaps. The
jklö spec stays the default.

| Action | Templates |
|---|---|
| Move | `h j k l` |
| Line start / end | `0` or `^` / `$` |
| Insert at start / end | `I` / `A` |
| Search forward | `/` |
| Repeat char jump | `ö` on QWERTZ, `;` on QWERTY |
| Line above / below | `-` / `+` on QWERTY |

---

## 4. Modes and state

### Opening

A note **always** opens in NORMAL, empty notes included. A search result still
places the cursor on its match. The pinned note gets the same engine.

### Mode chip and hints

The chip shows `NORMAL`, `INSERT`, `VISUAL`, `V-LINE` or `FLASH`. The hint line is
rewritten from the configured keys.

### `escape` order

1. Cancel a pending operator, VISUAL, search prompt or vim_flash.
2. Clear search highlights.
3. Close the note, from plain NORMAL only.

From INSERT, `escape` goes to NORMAL.

### Cursor

Clamped to the last character in NORMAL and VISUAL. Keeps 4 lines of context above
and below the cursor (LazyVim's `scrolloff = 4`). The adapter implements this, as
`TextArea` doesn't offer it.

### Registers

One internal register holding the text and a linewise flag, for the whole app
session, so a yank in one note pastes in another.

- `y` also copies to the system clipboard. `d`, `c` and `x` don't.
- `p` uses the register, unless the system clipboard has changed since the last
  yank. Then it pastes the clipboard through the existing paste path.
- `p` always pastes text. Attaching files stays on `ctrl+v`.

### Undo

- Each NORMAL command is one step. A whole INSERT session is one step.
- Up to 1000 steps. `TextArea`'s 2-second and 100-character batching must not split
  steps.
- `u` / `C-r` only. `ctrl+z`, `ctrl+y` and `super+z` do nothing in a note, and must
  not reach the panes behind it.
- INSERT has no undo key: `escape`, then `u`.

---

## 5. Search and vim_flash

### `?` search (LazyVim behaviour)

- Plain text, not patterns. Ignores case unless the search has a capital (smartcase).
- The prompt is in the hint line. The first match is highlighted and scrolled to
  while typing.
- `enter` confirms. `escape` cancels and restores the cursor.
- Matches raw text, including a link's hidden URL. The line goes raw when the cursor
  lands there.
- `n` always goes forward and `N` always backward. Both wrap and say so in the hint
  line. With no search yet, they report that.
- `*` is whole word and ignores case (smartcase doesn't apply).
- Highlights stay until the next search or `escape`.
- The last search lasts for the app session. There's no history.

### `s` vim_flash (flash.nvim behaviour)

- Each typed character narrows the matches. Search mode is exact, with smartcase.
- Searches visible text as drawn: a link matches on its name, not its URL. Only the
  note on screen is searched.
- Labels go after the match. Closer targets get labels first. Uppercase labels are
  allowed. A label never continues the search text.
- Pressing a label jumps. `enter` jumps to the first match. `escape` cancels. A single
  match doesn't jump by itself.
- Labels come from `api.vars.vim_flash_alphabet`, with the same default letters as
  the pane's `flash_alphabet` but as a separate setting.
- Works after operators (`ds`) and in VISUAL.

---

## 6. Slices

Each slice is test-first and adds pure engine tests plus some pilot tests for the
adapter. Each ships a demo project in this worktree's database, as `CLAUDE.md`
requires. New test files go in `tests/features.py`, and the `vim` marker goes in
`pyproject.toml`.

| # | Slice | Contains | Depends on |
|---|---|---|---|
| 0 | Markdown storage | Section 2: format, migration, backup, cursor-line rendering, search and copy, INSERT behaviour, test rewrites. Existing keys still work | none |
| 1 | Engine core | Package, `Buffer`, adapter, `api.vim.keys`, default keymap, always-open-NORMAL, chip and hints, `escape` order, clamping, scrolloff, motions, counts, `gx`, `gf`, old-key removal, layout templates | 0 |
| 2 | Operators and text objects | Grammar, `d c y > <`, `dd cc yy D C x r`, insert commands, text objects | 1 |
| 3 | Registers and undo | Register, clipboard rules, `p P`, undo grouping, `u C-r`, `ctrl+z`/`ctrl+y` removal in the note | 2 |
| 4 | Visual modes | `v V`, raw selected lines, `o`, auto-enter from shift or mouse | 2, 3 |
| 5 | Search | `? * n N`, highlights, `gn` and `cgn` family | 2, 4 for `vgn` |
| 6 | vim_flash | `s`, labels, overlay drawing, operator and VISUAL use | 2, 4 |
| 7 | App-wide undo keys | Panes: `u` / `C-r` for undo / redo, Bin restore moves from `u` to `R`, `ctrl+z` / `ctrl+y` removed | none, independent |

Slice 7 is the one change outside the note feature.

Test impact:

- Slice 0: `test_note_markdown.py` and much of `test_note_ui.py`, plus
  `tests/test_core/test_links.py` where it relies on the stored format.
- Slice 1: 21 lines in `test_note_ui.py` press keys whose meaning changes, and the
  Karabiner and keyboard-layout tests drive the editor.
- Slice 7: about 12 test lines press `ctrl+z` / `ctrl+y`, and about 20 lines press
  `u`, some of them restore tests.

---

## 7. Out of scope

- `.` repeat. `cgn` works once; continue with `n` and `cgn`.
- `S` (flash.nvim's treesitter jump).
- `$` auto-indent operator.
- `W`, `B`, `E` motions. Only the `iW` / `aW` text objects exist.
- Search patterns and search history.
- Named registers.
- New markup.
- The task description adapter.
- **Docs and screenshots**, including `site/docs/guide/notes.md`, `undo-bin.md` and
  `site/scripts/screenshots.py`. These go stale until the later docs stage.

---

## 8. To check during implementation

1. **Rendering is the highest risk.** `FoldedDocument` must become aware of the cursor
   row, and `HangingDocument` must re-wrap as the cursor moves. Check that the view
   doesn't jump when a line above the viewport changes height.
2. **Screen-row motion between raw and rendered lines.** `k`/`l` cross lines whose
   drawn columns differ from stored ones, and a mouse click on a rendered line needs
   mapping from drawn to stored column.
3. **Overlay drawing.** Search highlights and vim_flash labels must land correctly on
   rendered lines. Needs one generic "overlay spans" hook in `NoteView`, which knows
   nothing about vim.
4. **flash.nvim details the README doesn't document.** Read its source for: whether an
   operator includes the target (set by mode), what happens with more matches than
   labels, and how labels are chosen.
5. **`ctrl+z` in a note.** Confirm with a test that it doesn't reach the panes after
   `TextArea`'s defaults are disabled.
