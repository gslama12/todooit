# todooit

## What this is

A standalone TUI todo manager: the personal dooit fork (upstream v3.3.4) and
the parts of dooit-extras its config actually uses, merged into one
installable package. Built on [Textual](https://textual.textualize.io/): todos
are grouped into a tree of projects, navigated with vim-like keybindings, and
stored in a SQLite database via SQLAlchemy. It is configured through a Python
config file, which makes bar, dashboard, colors, formatters and keybinds fully
scriptable. Both source histories are preserved in this repo's git log.

- `todooit/` — the app itself (was `dooit/dooit`)
- `todooit/extras/` — the companion widget/formatter library (was
  `dooit_extras`), trimmed to the formatters and bar widgets the config uses

## Goal

Extend todooit in **appearance** and **functionality** — better visuals
(layout, colors, tree rendering, bar/dashboard, formatters) and new behaviour
(keybinds, commands, todo/project features). Upstream parity is not a
constraint; this is a personal project meant to be customized.

Where changes go:

- Config-level customization (keybinds, formatters, layout, status bar, colors)
  → `todooit/utils/default_config.py`. There is **no** config file in
  `~/.config`; the plugin manager always loads `default_config.py`, so that
  file *is* the user's config.
- Structural / rendering changes → the package itself, e.g.
  `todooit/ui/widgets/renderers/base_renderer.py`, `todooit/ui/api/`.

## Data locations (deliberately kept from dooit)

todooit keeps dooit's platformdirs app name so it opens the same live data as
a dooit install: the real database is `~/.local/share/dooit/dooit.db`
**inside WSL** (CSS cache: `~/.cache/dooit`). Do not "rebrand" these paths —
that would orphan the user's data.

## Testing a change

Python tooling only works from WSL here, not from Windows. To try a change:

```bash
wsl                     # from the todooit folder
uv venv .venv && source .venv/bin/activate    # first time only
uv pip install -e .                           # first time only
todooit                 # launches the real instance (live database!)
```

Then test the change in that running instance. **Every change must be
exercised this way** before it counts as done — a change that only
type-checks is not done.

The dev dependency group cannot be synced inside WSL (`textual-dev` pulls
`aiohttp`, which needs a C compiler WSL lacks), so run the test suite from a
throwaway venv:

```bash
uv venv /tmp/ttest --python 3.14
VIRTUAL_ENV=/tmp/ttest uv pip install -e . pytest pytest-asyncio faker
/tmp/ttest/bin/python -m pytest tests -q
```

## Every change ships a demo project

At the end of each change, seed a project into the live database that
demonstrates the change, so it can be verified by just opening todooit — never
leave the user to type in example items by hand. Name it after the change
(e.g. `demo: priority icons`) and fill it with todos that actually hit the new
code path (overdue, high priority, nested, recurring, … — whatever the change
touches). Refresh or replace the demo project when iterating instead of piling
up new ones.

Seed with the API rather than raw SQL, from the same activated venv:

```bash
python - <<'PY'
from todooit.api import manager, Project
manager.connect()

p = Project()
p.save()                        # attaches to the root project
p.description = "demo: <what changed>"
p.save()

t = p.add_todo()
t.description = "an overdue, high-priority item"
t.set_priority(3)
t.save()
PY
```

Then relaunch todooit and confirm the demo project shows the change.

Before touching the db in any other way, copy it to `/tmp` first and work on
the copy.
