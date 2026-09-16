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

## Git Worktree Workflow

This repo is a **bare repo** at `<repo>.git` (no working tree of its own).
All work happens in worktrees living side by side at `<repo>.git/<branch-name>`,
including `dev` and `main`. There is no "main checkout" anymore, so `dev` and `main` must
also exist as their own worktrees (`<repo>.git/dev`, `<repo>.git/main`).

- For every user session you will work only **inside** a defined worktree that will be specified and created by the user.
- If the user does not specify a worktree path in the request, you 
  are allowed to create a worktree yourself with: `git worktree add <branch> -b <branch> dev`. Pick a short, descriptive branch name from the task (e.g. `fix-priority-icons`,
  `feat-recurring-todos`). Branches always branch from `dev`, never `main` or another feature branch. Never implement directly in `dev` or `main`!
- Assume you're in one worktree, not the main checkout - check with
  `git worktree list` / `git branch --show-current` before assuming repo state.
- Never switch branches inside a worktree: each is pinned to one branch. If
  the request clearly belongs to work already in progress on an existing
  worktree, reuse that one instead of creating a new one.
- Commiting change or removing a worktree (`git worktree remove`) is **not allowed**.
- Don't read/edit files outside the current worktree unless asked.
- `node_modules`, `.env`, `.venv` build artifacts, and dev-server ports are not shared between worktrees. DB migrations *are* shared project-wide (`docs/db.md`) - be careful running
  destructive ones from a feature worktree.
- Every worktree gets its **own todooit instance** (database, cache and venv)
  — see [Worktree instances](#worktree-instances). Use it for everything you
  run; never touch the live instance or another worktree's.
- If you are on windows, all git commands (including `git worktree add`/`repair`) and all shell work in this repo must run under WSL, **never** Windows Git Bash/MinGW, even if the Bash tool defaults there. If a `Bash` tool call resets cwd to a `c:\...` path, that call ran outside WSL - repeat it as `wsl -e bash -lc "..."`.
- If you are on a Mac or Linux machine, you can use the regular shell.

### Helper scripts

Both live in the `dev` worktree and the user runs them from there. They are the
user's tools, not yours — you never call them — but what they do decides where
you put things:

- `./test.sh <worktree>` launches the app from that worktree against that
  worktree's instance, then returns to `dev`. This is how the user tries out
  your change, and it opens **the same database you seeded**.
- `./clean.sh` deletes every `feat-*`/`fix-*` worktree that has no uncommitted
  changes, force-deletes its branch, and removes its instance directory.
  Uncommitted work is always kept, so leaving your change uncommitted (as
  required above) also keeps it safe from cleanup.


## Data locations

todooit's data is separate from any dooit install (paths resolved in
[todooit/paths.py](todooit/paths.py)):

- DB: `~/.local/share/todooit/todooit.db` **inside WSL**
- CSS cache: `~/.cache/todooit`
- config dir: `~/.config/todooit` (unused, see above)

Seeded 2026-09-09 from the old dooit database; the two have diverged since.
Nothing here touches `~/.local/share/dooit/`.

**Dev instance:** `TODOOIT_HOME=<dir>` relocates DB/cache/config into one
self-contained directory, so development never touches the live data. Unset,
`todooit` is the real instance. `todooit --dev` is shorthand for
`~/.local/share/todooit-dev`, but an explicit `TODOOIT_HOME` always wins over
it — which is what gives each worktree an instance of its own.

### Worktree instances

One instance per worktree, named after the worktree directory:

```
~/.local/share/todooit-wt/<worktree>/     # = TODOOIT_HOME
    todooit.db                            # that worktree's database
    cache/
    venv/                                 # that worktree's uv environment
```

**Derive it, never hardcode it.** From inside a worktree:

```bash
export TODOOIT_HOME="$HOME/.local/share/todooit-wt/$(basename "$PWD")"
export UV_PROJECT_ENVIRONMENT="$TODOOIT_HOME/venv"
```

Export those two at the top of every shell session you work in, and every
`uv run`, `uv sync`, seeding script and manual launch below lands in the right
place. Both directories are created on first use — there is nothing to set up
— and `./clean.sh` deletes them along with the worktree.

Two things that are easy to get wrong:

- **Never use the bare `~/.local/share/todooit-dev`.** It is shared across
  branches, so it carries whatever schema the last branch left behind, and a
  branch that changes the model will meet a database that does not match it.
  Plain `todooit --dev` with no `TODOOIT_HOME` set lands there — don't run it.
- **Keep the venv off `/mnt/c`.** `UV_PROJECT_ENVIRONMENT` points into the
  instance dir on ext4 for a reason: installing onto the drvfs mount is slow
  and can silently truncate packages, producing import errors (`module 'click'
  has no attribute 'group'`) that `uv sync` will not repair, because the
  recorded metadata still looks complete. A `.venv` inside a worktree is a
  leftover from the old layout; ignore it.

## Testing a change

Python tooling only works from WSL, not Windows.

```bash
wsl
cd <the worktree you are working in>
export TODOOIT_HOME="$HOME/.local/share/todooit-wt/$(basename "$PWD")"
export UV_PROJECT_ENVIRONMENT="$TODOOIT_HOME/venv"

uv run todooit --dev     # this worktree's code against this worktree's database
```

The first `uv run` builds the venv; after that it is instant. Nothing there
touches the live instance — that is plain `todooit` with `TODOOIT_HOME` unset,
which you should not run.

Exercise every change in that running instance — type-checking alone doesn't
count as done.

`textual-dev` (dev dep group) needs a C compiler WSL lacks, so run tests from
a throwaway venv instead:

```bash
uv venv /tmp/ttest --python 3.14
VIRTUAL_ENV=/tmp/ttest uv pip install -e . pytest pytest-asyncio faker
/tmp/ttest/bin/python -m pytest tests -q
```

`/tmp` is inside WSL, so that venv sits on ext4 as well — keep it there rather
than in the worktree, for the same reason.

**Only run tests relevant to the change** — not the whole suite — for small
changes.

## Every change ships a demo

Seed a project into **this worktree's** database (never live) that exercises
the new code path, named after the change (e.g. `demo: priority icons`).
Refresh/replace it when iterating rather than piling up new ones. This is the
same database the user opens with `./test.sh <worktree>`, so what you seed is
exactly what they will see. Seed via the API, not raw SQL:

```bash
export TODOOIT_HOME="$HOME/.local/share/todooit-wt/$(basename "$PWD")"
export UV_PROJECT_ENVIRONMENT="$TODOOIT_HOME/venv"

uv run python - <<'PY'
from todooit.api import manager, Project
manager.connect()               # no arg -> resolves to $TODOOIT_HOME's database

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

Then launch `uv run todooit --dev` and confirm it. Before touching any DB any
other way, copy it to `/tmp` first.

If a schema change leaves the instance database stale, throw it away instead of
migrating it by hand: `rm -rf "$TODOOIT_HOME"`, then re-seed. It is disposable
by design, which is the whole point of one per worktree.

## Every new feature needs tests

New functionality must be covered by the test suite; keep existing tests
up-to-date.