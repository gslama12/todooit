# Keybindings

::: tip Press `?`
`?` opens this list inside the app, grouped the same way and always matching
the keys you actually have — your own config included. `escape` closes it.
Inside a note, `space` `?` lists the note's own keys.
:::

![The help screen](/screenshots/help.svg)

The **Pane** column says where a binding works. Bindings with no pane of their
own work over both.

On a Mac, every `ctrl` binding below also works with `cmd`, once the terminal
passes `cmd` on. See [Cmd shortcuts on macOS](/guide/installation#cmd-shortcuts-on-macos)
for the WezTerm setup.

## Navigation

Laid out for a QWERTZ keyboard; for vim's `h` `j` `k` `l` see [Vim layouts](#vim-layouts).

| Key | What it does | Pane |
| --- | --- | --- |
| `j` | Move focus to the projects pane | both |
| `ö` | Move focus to the tasks pane | both |
| `k` | Move the cursor up | both |
| `l` | Move the cursor down | both |
| `gg` | Move the cursor to the top of the list | both |
| `G` | Move the cursor to the bottom of the list | both |
| `f` | [Flash](/guide/search-move#flash): label every row on screen, type a label to jump there | both |
| `h` | Fold / unfold the highlighted item | both |
| `gt` | Jump to Today, on the first task scheduled for it | both |
| `gu` | Jump to Upcoming, on the nearest day's first task | both |
| `gb` | Jump to the Bin, on the task thrown away last | both |
| `gi` | Jump to the highlighted task in the project it is filed under | tasks |

## Editing

| Key | What it does | Pane |
| --- | --- | --- |
| `e` | Edit the description, with [vim keys](/guide/vim#task-descriptions) | both |
| `d` | Edit the due date | both |
| `s` | Edit the scheduled date | both |
| `r` | Edit the recurrence | both |
| `n` | Add a sibling | both |
| `N` | Add a child | both |
| `C` | [Quick add](/guide/quick-add): a whole task in one line | both |
| `space` | Open the task's [note](/guide/notes) | both |
| `m` | Open the pinned note, which belongs to no task | both |
| `c` | Tick the task off / back on | tasks |
| `p0`–`p3` | Priority: `p1` most urgent, `p3` least, `p0` clears it | both |
| `c0`–`c9` | Color the project and everything under it; the same key again takes it off | projects |
| `xx` | Move the highlighted item to the Bin | both |
| `R` | Restore it out of the Bin | both |
| `yy` | Delete it for good (asks first) | both |
| `YY` | Delete everything in the Bin, when it is open (asks first) | both |
| `u` | Undo the last change in the panes | both |
| `ctrl+r` | Redo | both |

The color slots are `c0` red, `c1` blue, `c2` green, `c3` yellow, `c4` orange,
`c5` purple, `c6` cyan, `c7` pink, `c8` brown, `c9` olive.

## Moving & clipboard

| Key | What it does | Pane |
| --- | --- | --- |
| `K` | Shift the highlighted item up | both |
| `L` | Shift the highlighted item down | both |
| `I` | Indent: make it a child of the item above | both |
| `U` | Unindent: take it out one level | both |
| `M` | Move the task to another project | tasks |
| `ctrl+c` | Copy the description to the clipboard | both |
| `ctrl+n` | Copy the task's note to the clipboard | both |
| `ctrl+v` | Add an item described by whatever is on the clipboard | both |

## Search & view

| Key | What it does | Pane |
| --- | --- | --- |
| `/` | [Find](/guide/search-move#finder) a task anywhere and jump to it; `>` first searches notes | both |
| `o` | Open the first link in the highlighted row | both |
| `SP` / `SD` / `SS` | Sort the tasks by priority / due date / scheduled date | both |
| `.` | Show / hide completed tasks in their projects | both |
| `?` | Show every key | both |
| `q` | Quit | both |

## Inside an edit

| Key | What it does |
| --- | --- |
| `enter` | Keep the edit |
| `escape` | In a date or recurrence field: throw it away. In a description: see [Vim editing](/guide/vim#task-descriptions) |
| `cal` | In a date field: open the [calendar](/guide/dates#the-calendar-picker) |

## Inside a note

A note is edited with vim's keys: NORMAL, INSERT, VISUAL, operators, text
objects, search and flash. See [Vim editing](/guide/vim) for the list, or
press `space` `?` in a note.

## Vim layouts

The defaults are laid out for a **QWERTZ** keyboard: the direction keys are
`j` `k` `l` `ö`, one key to the right of vim's, so the hand stays where it
types. A few note keys are moved to where a German keyboard has room for them
too (`=` `_` `ü` `ä` `h` `H` `?`).

The repo's [`config/`](https://github.com/gslama12/todooit/tree/main/config)
folder has two drop-in configs that put everything back on **standard vim
keys**:

| File | For | Fold / unfold | Shift down |
| --- | --- | --- | --- |
| `qwertz_vim.py` | QWERTZ keyboards | `ö` | `J` |
| `qwerty_vim.py` | QWERTY keyboards (which have no `ö`) | `;` | `J` |

The panes move with `h` `j` `k` `l`, and so do the note window, the calendar
(months on `H` / `L`), the help screen and the attachment strip. Inside a note
and a description, both switch to vim's own keys:

| Note action | Default | Both vim layouts |
| --- | --- | --- |
| Left / down / up / right | `j` `l` `k` `ö` | `h` `j` `k` `l` |
| Line start / first non-blank / line end | — / `=` / `_` | `0` / `^` / `$` |
| Line above / below (first non-blank) | `ü` / `ä` | `-` / `+` |
| Repeat / reverse `f` `F` `t` `T` | `h` / `H` | `;` / `,` |
| Search | `?` | `/` |

```bash
mkdir -p "$(dirname "$(todooit config-loc)")"
cp config/qwerty_vim.py "$(todooit config-loc)"
```

Or try one out first with `todooit -c config/qwerty_vim.py`.

## Changing them

Every binding above is set in `todooit/utils/default_config.py` and can be
overridden from your own config file — see
[Configuration](/reference/configuration#keybindings).
