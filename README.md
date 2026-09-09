# todooit

A beautiful, versatile todo app in your terminal for a keyboard based workflow. Started as a fork of "Dooit" extended with many features of "Todoist".

## Todoist Features

Added on top of the dooit fork:

- **Today / Upcoming / Completed / Bin** — fixed projects built from the real ones, jumped to with `gt`, `gu`, `gc`, `gb`, each with its own grouping.
- **Bin instead of deletion** — `xx` throws a task away, `u` fetches it back, `yy` deletes one for good and `YY` empties the whole Bin.
- **Quick add** — `C` types a whole task in one line, with its project, labels, priority and day, from wherever the cursor happens to be.
- **Finder** — `/` searches every task in the database, not just the pane in front, and walks the cursor over to the one that is picked.
- **Notes** — every task carries a note (`space`) with an insert mode, selection, copy and paste, and headings; `m` opens a pinned scratchpad note for thoughts with no task yet.
- **Link opening** — `o` opens the link under the cursor, on a task row and inside a note alike.
- **Priority `p0`-`p3`** — Todoist's scale, typed as a chord and shown as a colored checkbox rather than a column of its own.
- **Effort `e0`-`e3`** — the same kind of scale for how big a job is, colored green through red.
- **Natural language dates** — due and scheduled dates are typed as words, shown with their day name, and colored green through red as they come closer.
- **Recurrence on the scheduled date** — a recurring task moves its scheduled date on instead of carrying a due date.
- **Projects as folders** — projects nest and count their children, and a nested task is only completed once all of its children are.
- **Moving tasks** — `I` / `U` file a task under the one above it or pull it back out, and `ctrl+c` / `ctrl+v` copy and paste through the system clipboard.
- **Sorting** — `SP`, `SD`, `SS` read a project by priority, due date or scheduled date.
- **Help screen** — `?` held down shows every keybind, grouped by what it is for.
- **Reworked look** — Tokyo Night colors, a status bar with the current mode, icons, headers, rounded lines, alternating row shading (`q`), and completed tasks struck through and grayed out.

## Install & run

Pick whichever environment manager you already use; each installs the app editable, so editing the source is editing the running app.

With [uv](https://docs.astral.sh/uv/):

```bash
uv venv .venv && source .venv/bin/activate
uv pip install -e .
todooit
```

With the standard library's `venv`:

```bash
python3 -m venv .venv && source .venv/bin/activate
pip install -e .
todooit
```

With conda:

```bash
conda create -n todooit python=3.12 && conda activate todooit
pip install -e .
todooit
```

## Layout

- `todooit/` — the app: a Textual TUI, todos in a tree of projects, SQLite via SQLAlchemy
- `todooit/extras/` — formatter / status-bar widget library (merged in from dooit-extras, trimmed to what the config uses)
- `todooit/utils/default_config.py` — the configuration: keybinds, formatters, bar, dashboard, colors
- `tests/` — the test suite (`python -m pytest tests`)

## Data

Todos live in `~/.local/share/todooit/todooit.db`, with generated CSS cached in `~/.cache/todooit`. This is todooit's own database: a dooit install alongside it keeps its own, untouched.

## Credits

MIT licensed. Based on [dooit](https://github.com/dooit-org/dooit) (upstream v3.3.4) and [dooit-extras](https://github.com/dooit-org/dooit-extras) by kraanzu and contributors; both source histories are preserved in this repo's git log.
