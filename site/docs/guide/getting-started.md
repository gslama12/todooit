# Getting started

Not installed yet? [Installation](/guide/installation) is a one-liner.

Run `todooit`. It opens on the **Today** pane.

![The Today pane](/screenshots/today.svg)

Two panes: projects on the left, the tasks of the highlighted project on the
right. A status bar underneath shows the mode, the current project, the time
and the date.

## The keys you need first

| Key | What it does |
| --- | --- |
| `j` | Focus the projects pane |
| `ö` | Focus the tasks pane |
| `k` / `l` | Move up / down |
| `?` | **Show every key** |

::: warning Not vim's hjkl
`j` and `ö` move *between panes*; `k` and `l` move *up and down* — one key to
the right of vim's, for a QWERTZ keyboard. If you want vim's own `h` `j` `k` `l`
(and vim's keys inside notes), use one of the
[vim layouts](/guide/keybindings#vim-layouts).
:::

## Your first task

```
j        focus the projects pane
n        add a project, type its name, enter
ö        cross into its tasks
n        add a task, type it, enter
c        tick it off
```

`i` and `a` add one too, the same as `n`.

## Then

- `C` adds a whole task in one line — see [Quick add](/guide/quick-add).
- `s` and `d` set the scheduled and due dates, typed as words; `r` repeats a
  task — see [Dates & recurrence](/guide/dates).
- `N` adds a child task and `h` folds it shut — see [Steps](/guide/tasks#steps).
- `e` edits a description with vim keys — see [Vim editing](/guide/vim).
- `space` opens the task's note, `m` a note pinned to nothing at all — see
  [Notes](/guide/notes).
- `gt` `gu` `gb` jump to Today, Upcoming and the Bin — see
  [Projects & panes](/guide/projects#the-three-fixed-projects).
- `f` labels every row on screen to jump to, `/` finds any task in the
  database — see [Search, flash & move](/guide/search-move).
- `xx` throws a task away and `u` undoes the last change — see
  [Undo & the Bin](/guide/undo-bin).
- `q` quits. `ctrl+c` is a copy here, as it is everywhere else.

The whole list of keys is on [Keybindings](/guide/keybindings), and `?` shows
it in the app.
