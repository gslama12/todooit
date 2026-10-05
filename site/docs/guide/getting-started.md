# Getting started

Not installed yet? [Installation](/guide/installation) is a one-liner.

Run `todooit`. It opens on the **Today** pane.

![The Today pane](/screenshots/today.svg)

Two panes: projects on the left, the tasks of the highlighted project on the
right. A status bar underneath shows the mode, the current project, the time
and the date.

## The four keys you need first

| Key | What it does |
| --- | --- |
| `j` | Focus the projects pane |
| `ö` | Focus the tasks pane |
| `k` / `l` | Move up / down |
| `?` | Show the help screen (hold it) |

::: warning Not vim's hjkl
`j` and `ö` move *between panes*; `k` and `l` move *up and down*. The same
four keys work inside a note.
:::

## Your first task

```
j        focus the projects pane
n        add a project, type its name, enter
ö        cross into its tasks
n        add a task, type it, enter
c        tick it off
```

## Then

- `C` adds a whole task in one line — see [Quick add](/guide/quick-add).
- `s` and `d` set the scheduled and due dates, typed as words; `r` repeats a
  task — see [Dates & recurrence](/guide/dates).
- `N` files a step under a task and `h` folds it shut — see
  [Steps](/guide/tasks#steps).
- `space` opens the task's note, `m` a note pinned to nothing at all — see
  [Notes](/guide/notes).
- `gt` `gu` `gc` `gb` jump to Today, Upcoming, Completed and the Bin — see
  [Projects & panes](/guide/projects#the-four-fixed-projects).
- `/` finds any task in the database and `M` files one under another project
  — see [Search, move & clipboard](/guide/search-move).
- `xx` throws a task away and `ctrl+z` takes back the last change — see
  [Undo & the Bin](/guide/undo-bin).
- `q` quits. `ctrl+c` is a copy here, as it is everywhere else.

The whole list of keys is on [Keybindings](/guide/keybindings), and `?` shows
the same list in the app.
