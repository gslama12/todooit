# Keybindings

Hold `?` in the app for the same list, grouped the same way.

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
| `ö` | Move focus to the todos pane | both |
| `k` | Move the cursor up in the focused list | both |
| `l` | Move the cursor down in the focused list | both |
| `gg` | Move the cursor to the top of the list | both |
| `G` | Move the cursor to the bottom of the list | both |
| `h` | Toggle the expansion of the highlighted item | both |
| `gt` | Jump to Today, on the first task scheduled for it | both |
| `gu` | Jump to Upcoming, on the nearest day's first task | both |
| `gc` | Jump to Completed, on the task finished last | both |
| `gb` | Jump to the Bin, on the task thrown away last | both |
| `gi` | Jump to the highlighted task in the project it is filed under | todos |

## Editing

| Key | What it does | Pane |
| --- | --- | --- |
| `i` | Start editing the description of the focused item | both |
| `d` | Start editing the due date of the todo | both |
| `s` | Start editing the scheduled date of the todo | both |
| `r` | Start editing the recurrence of the todo | both |
| `n` | Add a sibling to the highlighted item | both |
| `N` | Add a child to the highlighted item | both |
| `C` | Type a whole task in one line: project, priority and day | both |
| `space` | Show and edit the note of the todo | both |
| `m` | Write in the pinned note, which belongs to no task | both |
| `c` | Toggle the completion of the todo | todos |
| `a` | Mark the todo as handed to an AI, or take the mark back off | both |
| `p0`–`p3` | Set the priority: `p1` most urgent, `p3` least, `p0` clears it | both |
| `c0`–`c9` | Color the project and everything under it; the same key again takes it off | projects |
| `xx` | Move the highlighted item to the Bin | both |
| `u` | Restore the highlighted item out of the Bin | both |
| `yy` | Delete the highlighted item for good (asks first) | both |
| `YY` | Delete everything in the Bin or Completed for good, whichever is open (asks first) | both |
| `ctrl+z` | Take back the last change made in the panes | both |
| `ctrl+y` | Put back the change that was last taken back | both |

The color slots are `c0` red, `c1` blue, `c2` green, `c3` yellow, `c4` orange,
`c5` purple, `c6` cyan, `c7` pink, `c8` brown, `c9` olive.

## Moving & clipboard

| Key | What it does | Pane |
| --- | --- | --- |
| `K` | Shift the highlighted item up | both |
| `L` | Shift the highlighted item down | both |
| `I` | Make the highlighted task a step of the task above it | both |
| `U` | Take the highlighted task out of the task it is a step of | both |
| `M` | File the highlighted task under another project | todos |
| `ctrl+c` | Copy the description of the focused item to the clipboard | both |
| `ctrl+n` | Copy the note of the highlighted todo to the clipboard | both |
| `ctrl+v` | Add an item described by whatever is on the clipboard | both |

## Search & view

| Key | What it does | Pane |
| --- | --- | --- |
| `/` | Find a task anywhere in the tree and jump to it | both |
| `o` | Open the first link written in the highlighted row | both |
| `SP` / `SD` / `SS` | Sort the todos by priority / due date / scheduled date | both |
| `?` | Show the help screen (while held) | both |
| `q` | Quit | both |

## Inside an edit

| Key | What it does |
| --- | --- |
| `enter` | Keep the edit |
| `escape` | Throw it away |
| `cal` | In a date field: open the [calendar](/guide/dates#the-calendar-picker) |

## Inside a note

See [Notes](/guide/notes#two-modes).

## Vim layouts

The defaults are laid out for a **QWERTZ** keyboard: the direction keys are
`j` `k` `l` `ö`, one key to the right of vim's, so the hand stays where it
types. The repo's [`config/`](https://github.com/gslama12/todooit/tree/main/config)
folder has two drop-in configs that put them back on vim's `h` `j` `k` `l`:

| File | For | Fold / unfold | Shift down |
| --- | --- | --- | --- |
| `qwertz_vim.py` | QWERTZ keyboards | `ö` | `J` |
| `qwerty_vim.py` | QWERTY keyboards (which have no `ö`) | `;` | `J` |

Everything else stays as listed above. The note window, the calendar, the help
screen and the attachment strip steer with whatever the panes move with, so
they switch to `h` `j` `k` `l` too (and the calendar's months to `H` / `L`).

```bash
mkdir -p "$(dirname "$(todooit config-loc)")"
cp config/qwerty_vim.py "$(todooit config-loc)"
```

Or try one out first with `todooit -c config/qwerty_vim.py`.

## Changing them

Every binding above is set in `todooit/utils/default_config.py` and can be
overridden from your own config file — see
[Configuration](/reference/configuration#keybindings).
