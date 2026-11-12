# todooit

[![Docs](https://img.shields.io/badge/docs-todooit-7AA2F7?style=flat-square&logo=readthedocs&logoColor=white)](https://gslama12.github.io/todooit/)
[![License: MIT](https://img.shields.io/badge/license-MIT-9ECE6A?style=flat-square)](LICENSE)

A keyboard-driven todo app for the terminal: todos in a tree of projects, vim-like
keys, markdown notes with vim editing, natural-language dates and search. Started as a fork of
[dooit](https://github.com/dooit-org/dooit) and extended with the parts of Todoist
it was missing.

<p align="center">
  <img src="site/docs/public/demo.gif" alt="todooit" width="900">
</p>

## Features

- **Fixed views** — Today, Upcoming and a Bin, built from your real projects and jumped to with `gt` / `gu` / `gb`.
- **Done stays put** — a ticked task stays in its project, hidden; `.` shows completed tasks in place, struck through.
- **Nested projects and tasks** — both nest as deep as you want; `h` folds, `I` / `U` indent. A task's dates hold its steps: planning a task plans its steps, and no step is due after its task.
- **Dates in words** — scheduled (`s`) and due (`d`) typed as `tom`, `next friday`, `in 2w`, `eom`, `19.07.`, or picked off a calendar (`cal`).
- **Smart recurrence** — `r` repeats a task every `3d`, `2w`, `1m`, or on the last *working* day of the month with `eom`.
- **Flash jumps** *(new)* — `f` labels every row on screen; type a label and the cursor is there.
- **Markdown notes** — every task has a note (`space`) with headings, quotes, emphasis, bullets and numbered lists that continue and renumber themselves; `m` opens a pinned scratchpad.
- **File attachments** — copy a file anywhere and `ctrl+v` it into a note; it is pinned to the note by path.
- **Vim editing** — notes are edited with real vim keys (motions, operators, text objects, VISUAL, search & replace, flash), and `e` edits a task's description with the same keys.
- **Quick add** — `C` types a whole task in one line, with its project, priority and day.
- **Finder** — `/` searches every task in the database and walks the cursor to the one you pick; start with `>` to search inside notes.
- **The small things** — `xx` to the Bin and `R` back, `u` / `ctrl+r` undo and redo everything, `ctrl+c` / `ctrl+v` copy and paste tasks, `ctrl+n` copies a note, `M` moves a task to another project, `SP` / `SD` / `SS` sort, `o` opens a link, `c0`–`c9` color a project.

> [!TIP]
> **Press `?` for a list of every key**, always matching your config. Inside a note, `space` `?` lists the note's vim keys. More in the [documentation](https://gslama12.github.io/todooit/).


## Install

Needs Python 3.9+ on macOS, Linux or WSL, and a
[Nerd Font](https://www.nerdfonts.com/font-downloads) in your terminal. Tested on [WezTerm](https://wezterm.org/).

```bash
uv tool install todooit
todooit  # run from anywhere
```

Also check out the [installation guide](https://gslama12.github.io/todooit/guide/installation).

## Keyboard layout

The default keys are set up for a **QWERTZ** keyboard, with `j` `k` `l` `ö` as the navigation keys (one key to the right of vim's `h` `j` `k` `l`), and a few note keys moved to where a German keyboard has room for them.

| Key | Moves |
| --- | --- |
| `j` / `ö` | To the projects / tasks pane |
| `k` / `l` | Up / down |

The [`config/`](config/) folder has two drop-in configs that switch everything to
**standard vim keys** instead — `qwertz_vim.py` and `qwerty_vim.py`: `h` `j` `k` `l`
in the panes, and vim's own `0` `^` `$` `-` `+` `;` `,` `/` inside notes.

```bash
mkdir -p "$(dirname "$(todooit config-loc)")"
cp config/qwerty_vim.py "$(todooit config-loc)"
```

or try it out first with `todooit -c config/qwerty_vim.py`. See
[Vim layouts](https://gslama12.github.io/todooit/guide/keybindings#vim-layouts).


## Configuration

Keybinds, colors, columns and the status bar are all set in Python
in `todooit/utils/default_config.py`, and your own file on top of it overrides any
of them — see [Configuration](https://gslama12.github.io/todooit/reference/configuration).


## Data

Todos live in `~/.local/share/todooit/todooit.db`, with generated CSS cached in
`~/.cache/todooit` and an optional config file in `~/.config/todooit`. 

> Setting `TODOOIT_HOME` moves all three into that one directory instead, giving a fully isolated instance; `todooit --dev` is shorthand for one at `~/.local/share/todooit-dev`, handy for trying changes out without touching your real todos.


### Coming from dooit

```bash
uv run python migration/db_migration.py            # reads ~/.local/share/dooit/dooit.db
uv run python migration/db_migration.py --dry-run  # what would move, nothing written
```

This copies a dooit v3 database (v3.0 to v3.3.4) into todooit's. The dooit file
is opened read-only, and an existing todooit database is only replaced with
`--force`, which backs it up first. Effort is dropped, minute recurrences round
up to hours, and each family of steps is fitted to todooit's rules (open steps
of a done task are completed, nested recurrences end). Details are in
[Migrating from dooit](https://gslama12.github.io/todooit/reference/data#migrating-from-dooit).


## Contributing

For development, install from source — editable, so editing the code edits the
running app:

```bash
git clone https://github.com/gslama12/todooit
cd todooit
uv venv .venv && source .venv/bin/activate
uv pip install -e .
todooit
```

Then:

```bash
uv sync
uv run pytest -q              # -m smoke -n 4 for the quick check
uv run todooit --dev          # the app against a throwaway database
```
More in [Development](https://gslama12.github.io/todooit/reference/development).


## Credits

MIT licensed. Based on [dooit](https://github.com/dooit-org/dooit) (upstream v3.3.4) and [dooit-extras](https://github.com/dooit-org/dooit-extras) by kraanzu and contributors; both source histories are preserved in this repo's git log.
