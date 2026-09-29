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
  `feat-recurring-todos`). Branches always branch from `dev`, never `main` or another feature branch. Never implement directly in `dev` or `main`.
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

All four are tracked in the repo, so every worktree carries its own copy.
They are the user's tools, not yours — you never call them — but what they do
decides where you put things:

- `bash test.sh`, run **from inside a worktree** with no arguments, launches
  the app from that worktree against that worktree's instance and leaves the
  user standing there. This is how the user tries out your change, and it
  opens **the same database you seeded**.
- `bash run_tests.sh`, run **from inside a worktree** with no arguments, asks
  what to run — smoke, the whole suite, one feature marker, one layer, one
  file, the last failures, a `-m` expression of the user's own, the CI command,
  or coverage — and runs it in that worktree's environment, printing the pytest
  command first. It is the menu form of [Which tests to run](#which-tests-to-run);
  you still run pytest yourself rather than calling this.
- `bash clean.sh`, run from anywhere inside the repo, deletes every
  `feat-*`/`fix-*` worktree that has no uncommitted changes, force-deletes its
  branch, and removes its instance directory; it prints the plan as a table
  and aborts untouched if the directory it was run from is on the remove list.
  Uncommitted work is always kept, so leaving your change uncommitted (as
  required above) also keeps it safe from cleanup.
- `bash push.sh`, run **from inside a worktree**, stages and commits
  everything there, merges the current `dev` into the branch, shows the
  commits and a `git diff --stat` of what would land, then asks and —
  on yes — fast-forwards `dev` onto the branch and pushes `dev`. Feature
  branches are never pushed and there is no pull request: work lands on `dev`
  from the user's machine. On conflicts it stops and lists them, in the feature
  branch. This is how the user ships your change — you still never commit
  yourself.


## Data locations

todooit's data is separate from any dooit install (paths resolved in
[todooit/paths.py](todooit/paths.py)):

- DB: `~/.local/share/todooit/todooit.db` **inside WSL**
- CSS cache: `~/.cache/todooit`
- config dir: `~/.config/todooit` (unused, see above)

todooit uses a different database schema than dooit and is therefore not
compatible with a dooit database.

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

Tests run from the worktree's own environment, the same one `uv run todooit`
uses — no separate venv:

```bash
export PYTHONPYCACHEPREFIX=/tmp/ttpyc   # optional: ~20% off start-up, and
                                        # keeps __pycache__ out of the worktree
uv run pytest -q
```

> `textual-dev` used to need a C compiler WSL lacks, which is why this used to
> say to build a throwaway venv under `/tmp`. `aiohttp` ships a wheel now
> (3.14.3), so `uv sync` resolves the dev group cleanly and the workaround is
> gone. If it ever comes back, the fix is a venv on ext4 with `-e .` plus
> `pytest pytest-asyncio pytest-xdist pytest-timeout faker`, run as
> `python -m pytest` so the cwd wins over its editable install.

**The environment is per worktree**, since `UV_PROJECT_ENVIRONMENT` points
into that worktree's instance dir. The root `conftest.py` fails the run
outright if the `todooit` being imported ever belongs to a different worktree
than the tests, so a stale environment is an error rather than a mystery.

Tests never touch your instance database, whatever `TODOOIT_HOME` is set to:
the root `conftest.py` overwrites it with a per-process directory under
`/tmp/todooit-tests/` before `todooit` is imported, which is also what keeps
parallel workers from writing over each other's CSS cache.

### Which tests to run

**Only run tests relevant to the change** — not the whole suite — for small
changes. Every test carries a marker for its feature, derived from its
filename (the table is [tests/features.py](tests/features.py)), so that rule
has a mechanical form:

```bash
uv run pytest -m smoke -n 4        # ~8s: all of test_core + one test per UI module
uv run pytest -m notes             # one feature, core and UI halves both
uv run pytest -m "notes and ui"    # just the UI half
uv run pytest -m "move or sort"    # a change that touches two
uv run pytest -n auto              # the whole thing, ~95s
uv run pytest tests/test_ui/test_bar.py  # a single file: no -n, xdist start-up dominates
```

`uv run pytest -m smoke -n 4` is the cheap "did I break the world" check; a typo in
`-m` is an error rather than a run that quietly selects nothing. A new test
file must be added to `tests/features.py` or `tests/test_meta.py` fails.

Two things the suite now relies on, worth keeping true:

- **Tests must stay independent of each other.** `-n auto` hands them out
  across processes in no particular order.
- **Never wait on the clock.** The app's own timers are stretched out of the
  way during tests, and a test that sleeps or counts on a debounce firing will
  fail under load. Wait for a state instead — `boot()`, or a helper like it.

## Every change ships a demo

Seed a project into **this worktree's** database (never live) that exercises
the new code path, named after the change (e.g. `demo: priority icons`).
Refresh/replace it when iterating rather than piling up new ones. This is the
same database the user opens with `bash test.sh` in this worktree, so what you seed is
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