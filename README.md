# todooit

[![Docs](https://img.shields.io/badge/docs-todooit-7AA2F7?style=flat-square&logo=readthedocs&logoColor=white)](https://gslama12.github.io/todooit/)
[![License: MIT](https://img.shields.io/badge/license-MIT-9ECE6A?style=flat-square)](LICENSE)

A keyboard-driven todo app for the terminal: todos in a tree of projects, vim-like
keys, notes, dates and search. Started as a fork of
[dooit](https://github.com/dooit-org/dooit) and extended with the parts of Todoist
it was missing.

<p align="center">
  <img src="site/docs/public/demo.gif" alt="todooit" width="900">
</p>

## Features

- **Fixed views** — Today, Upcoming, Completed and a Bin, built from your real projects and jumped to with `gt` / `gu` / `gc` / `gb`.
- **Projects and steps** — projects nest as deep as you want, and so do tasks. `h` folds a task shut; Projects act as folders.
- **Quick add** — `C` types a whole task in one line, with its project, priority and day.
- **Finder** — `/` searches every task in the database, not just the pane in front, and walks the cursor over to the one you pick. Start with `>` to search inside notes instead.
- **Notes** — every task carries a markdown note (`space`), and `m` opens a pinned scratchpad for thoughts with no task yet.
- **Note Attachments** — copy a file anywhere on your machine and `ctrl+v` in a note pins a refernce to it at the bottom of the note window.
- **Dates** — due and scheduled dates typed as words (`next friday`) or picked off a calendar (`cal`), and `r` makes a task recur.
- **Ordering** — `K` / `L` move a task, `I` / `U` nest it, `M` sends it to another project, and `SP` / `SD` / `SS` read a project by priority or date.
- **The small things** — `ctrl+c` / `ctrl+v` move tasks through the system clipboard, `o` opens the link under the cursor, `a` flags a task handed to an AI, `ctrl+z` takes back anything.

`?` shows all available keybinds. Also check the [Documentation](https://gslama12.github.io/todooit/) for more.


## Install

Needs Python 3.9+ on macOS, Linux or WSL, and a
[Nerd Font](https://www.nerdfonts.com/font-downloads) in your terminal. Tested on [WezTerm](https://wezterm.org/).

```bash
uv tool install todooit
todooit  # run from anywhere
```

Also check out the [installation guide](https://gslama12.github.io/todooit/guide/installation).

## Keyboard layout

The default keys are set up for a **QWERTZ** keyboard, with `j` `k` `l` `ö` as the navigation keys (one key to the right of vim's `h` `j` `k` `l`).

| Key | Moves |
| --- | --- |
| `j` / `ö` | To the projects / tasks pane |
| `k` / `l` | Up / down |

The [`config/`](config/) folder has two drop-in configs that switch to standard
vim navigation instead — `qwertz_vim.py` and `qwerty_vim.py`. 

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

This copies a dooit v3 database into todooit's. The dooit file is opened
read-only, and an existing todooit database is only replaced with `--force`,
which backs it up first. Effort is dropped, and minute recurrences round up to
hours. Details are in
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
