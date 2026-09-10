# todooit

## What this is

A standalone TUI todo manager: the personal dooit fork (upstream v3.3.4) plus
the parts of dooit-extras its config uses, merged into one installable
package. Built on [Textual](https://textual.textualize.io/): todos are grouped
into a tree of projects, navigated with vim-like keybindings, stored in
SQLite via SQLAlchemy, and configured through a scriptable Python config
file. Both source histories are preserved in this repo's git log.

- `todooit/` — the app itself (was `dooit/dooit`)
- `todooit/extras/` — companion widget/formatter library (was `dooit_extras`),
  trimmed to what the config uses

## Goal

Extend todooit in **appearance and functionality**. Upstream parity is not a
constraint — this is a personal project meant to be customized.

- Config-level changes (keybinds, formatters, layout, bar, colors) →
  `todooit/utils/default_config.py`. There is no `~/.config` file — the
  plugin manager always loads `default_config.py`, so that file *is* the
  user's config.
- Structural/rendering changes → the package itself, e.g.
  `todooit/ui/widgets/renderers/base_renderer.py`, `todooit/ui/api/`.

## Git worktrees

This repo runs multiple parallel Claude Code sessions via git worktrees, one
branch each, under `../<repo>-trees/<branch-name>`.

- Assume you're in one worktree, not the main checkout — check with
  `git worktree list` / `git branch --show-current` before assuming repo state.
- New feature branches always branch from `dev`, never `main` or another
  feature branch: `git worktree add ../<repo>-trees/<branch> -b <branch> dev`.
- Never switch branches inside a worktree; each is pinned to one branch. Ask
  the user first if a different branch is needed.
- Don't `git worktree add/remove` without user confirmation.
- Don't read/edit files outside the current worktree unless asked.
- Confirm you're not on `main`/`dev` before committing.
- `node_modules`, `.env`, build artifacts, and dev-server ports are **not**
  shared between worktrees — check/set up per worktree, don't assume. DB
  migrations *are* shared project-wide (`docs/db.md`) — be careful running
  destructive ones from a feature worktree.

## Data locations

todooit's data is separate from any dooit install (paths resolved in
[todooit/paths.py](todooit/paths.py)):

- DB: `~/.local/share/todooit/todooit.db` **inside WSL**
- CSS cache: `~/.cache/todooit`
- config dir: `~/.config/todooit` (unused, see above)

Seeded 2026-09-09 from the old dooit database; the two have diverged since.
Nothing here touches `~/.local/share/dooit/`.

**Dev instance:** `TODOOIT_HOME=~/.local/share/todooit-dev` (shorthand:
`todooit --dev`) relocates DB/cache/config into one self-contained directory,
so development never touches the live data. Unset, `todooit` is the real
instance.

## Testing a change

Python tooling only works from WSL, not Windows.

```bash
wsl
uv venv .venv && source .venv/bin/activate    # first time only
uv pip install -e .                           # first time only
todooit                                       # launches the real instance — live DB!
```

Exercise every change in that running instance — type-checking alone doesn't
count as done.

`textual-dev` (dev dep group) needs a C compiler WSL lacks, so run tests from
a throwaway venv instead:

```bash
uv venv /tmp/ttest --python 3.14
VIRTUAL_ENV=/tmp/ttest uv pip install -e . pytest pytest-asyncio faker
/tmp/ttest/bin/python -m pytest tests -q
```

**Only run tests relevant to the change** — not the whole suite — for small
changes.

## Every change ships a demo

Seed a project into the **dev** database (never live) that exercises the new
code path, named after the change (e.g. `demo: priority icons`). Refresh/
replace it when iterating rather than piling up new ones. Seed via the API,
not raw SQL:

```bash
TODOOIT_HOME=~/.local/share/todooit-dev python - <<'PY'
from todooit.api import manager, Project
manager.connect()               # no arg -> resolves to the dev database

p = Project()
p.save()
p.description = "demo: <what changed>"
p.save()

t = p.add_todo()
t.description = "an overdue, high-priority item"
t.set_priority(3)
t.save()
PY
```

Then launch `todooit --dev` and confirm it. Before touching any DB any other
way, copy it to `/tmp` first.

## Every new feature needs tests

New functionality must be covered by the test suite; keep existing tests
up-to-date.