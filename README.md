# todooit

A beautiful, versatile todo app in your terminal for a keyboard based workflow. Started as a fork of "Dooit" extended with many features of "Todoist".

## Install & run

```bash
uv venv .venv && source .venv/bin/activate
uv pip install -e .
todooit
```

## Layout

- `todooit/` — the app: a Textual TUI, todos in a tree of projects, SQLite via SQLAlchemy
- `todooit/extras/` — formatter / status-bar widget library (merged in from dooit-extras, trimmed to what the config uses)
- `todooit/utils/default_config.py` — the configuration: keybinds, formatters, bar, dashboard, colors
- `tests/` — the test suite (`python -m pytest tests`)

## Data

todooit keeps dooit's on-disk app name, so an existing dooit database is picked up as-is from `~/.local/share/dooit/dooit.db`.

## Credits

MIT licensed. Based on [dooit](https://github.com/dooit-org/dooit) (upstream v3.3.4) and [dooit-extras](https://github.com/dooit-org/dooit-extras) by kraanzu and contributors; both source histories are preserved in this repo's git log.
