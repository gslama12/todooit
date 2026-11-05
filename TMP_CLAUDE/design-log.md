# vim-engine design log

Base: `feat-vim-module`, branched from `dev` (bd5559be).

## Settled in round 1

- Q1: pure package `todooit/vim_engine/`, no Textual imports, acts on a `Buffer`
  protocol. `note/vim/` becomes a thin adapter. A single-line adapter comes later.
- Q2: edits outside `vim/` are fine when the feature needs them. Unrelated parts
  of the app stay untouched.
- Q3: `gx` opens links, `gf` picks files, half page is only `C-u`/`C-d`. `C-d`
  clears the note only in INSERT. The spec overrides current behaviour (`0`/`$`).
- Q4: keybinds configurable in config; the initial spec is the default.
- Q5: LazyVim-style. Edits always act on the underlying text; other lines are
  drawn rendered, the cursor line shows raw markup.
- Q6: the spec is the user's own custom mapping and is correct as written.
  `A` = start, `I` = end, `?` = forward, `$` = auto-indent operator.
- Q7: internal register (stored text + linewise flag), app-session lifetime. `y`
  mirrors to the system clipboard as markdown; `d`/`c`/`x` don't. `p` uses the
  register unless the clipboard changed, then the markdown paste path.
- Q8: slices on one branch, test-first. Note flash must be clearly named apart
  from the task-pane `FlashJump`. The user handles TMP_CLAUDE before pushing.

## Findings behind round 2

- Notes are stored already drawn: bullet glyphs, quote bar glyph, title + rule
  line, zero-width-space emphasis. `typed.py` converts at typing time and
  `disp/markdown.py` translates at the clipboard. Q5 therefore implies a storage
  change and a data migration.
- Note text consumers outside the note package: `screens/search.py`,
  `trees/todos_tree.py` (copy), `api/history.py`, `api/pinned_note.py`.
  `api/manager.py` already runs column upgrades on connect.
- `TextArea.edit` has no read_only check, so NORMAL-mode edits work without
  leaving read_only. Only the keyboard actions check it.
- `EditHistory` batches by a 2s timer and 100 characters, max 50 checkpoints.
- No app-level or priority bindings reach the note screen.
- 21 lines in `test_note_ui.py` press keys whose meaning changes. The Karabiner
  tests also drive the note editor.

## Settled in round 2

- Q10: store real markdown. One-way conversion of the DB at startup, with a
  backup outside the repo. Search works on the markdown text directly. Tests are
  rewritten.
- Q12: heading is one row, underlined across the window width. No new markup.
- Q13: INSERT table accepted (keep enter/tab/renumber/prefix carry-over; drop
  backspace specials; `cc` keeps the marker; `dd` removes the line and renumbers).
- Q14: `=`, `A`, `ü`, `ä` land on first non-blank. `k`/`l` move by screen row
  without a count, real line with one. `_` lands on the last character.
- Q15: `api.vim.keys` API accepted. Default is the jklö spec. `config/qwert*_vim.py`
  carry more vim-like mappings. Note keys go in the docs, not the help screen.
- Q16: name is `vim_flash`, not `seek`.
- Q17: no `S`. `aw` behaves as in default vim.
- Q18: `.` is removed from scope. `u` and `C-r` only. `ctrl+z`/`ctrl+y` go.
- Q19: slice 0 stays first. The user splits the work into tickets.

## Open: Q9 and Q11 were not answered in round 2.

## Findings

- `to_markdown` is stable when run twice on every old-format sample tried, and
  drops orphan emphasis marks. Nested numbers come out with a 3-space indent,
  while the note nests by 2, so the migration must normalise indent.
- Note undo isn't in app history: `history.py` excludes notes from snapshots and
  keeps deleted notes only in memory, so nothing persisted there needs converting.
- `search.py`'s LINE_MARKER already strips markdown prefixes.
- `ctrl+z`/`ctrl+y` are also the app-wide pane undo keys (`default_config.py:554`).

## Settled in round 3

- Q9: conflict table accepted. Q11: A (cursor line raw; selected lines raw in VISUAL).
- Q21: `gn` is a normal motion; `cgn`/`dgn`/`ygn`/`vgn` work. No repeat.
- Q22: search behaves as in LazyVim. Q23: `s` behaves as flash.nvim.
- Q24: notes ALWAYS open in NORMAL, empty ones included. `$` auto-indent removed
  (`$` unbound). Docs and screenshots are out of scope. Rest of Q24 accepted.

## Research corrections

- LazyVim: ignorecase + smartcase; smartcase doesn't apply to `*`, so `*` ignores
  case. `n` always goes forward and `N` backward, whatever the search direction.
  `<esc>` clears highlights. scrolloff = 4. hlsearch/incsearch/wrapscan are left
  at Neovim defaults.
- flash.nvim defaults: mode exact; autojump off; label after match; uppercase
  labels allowed; `<CR>` jumps to the first match; closer targets labelled first;
  labels never continue the pattern; inclusive is set by mode. The README doesn't
  document what happens with more matches than labels, or the label algorithm.

## Open: Q20 (whole-app undo keys), search pattern syntax, scrolloff.

## Settled after to-spec

- Q25: A. Q26: plain text search. Q27: scrolloff 4.
- Test seams: engine and note window only. No automated tests for migrating old
  databases.
