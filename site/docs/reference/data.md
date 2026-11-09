# Data & files

## Default locations

Resolved with [`platformdirs`](https://pypi.org/project/platformdirs/), so the
exact paths follow the platform. On Linux and WSL:

| What | Where |
| --- | --- |
| Database | `~/.local/share/todooit/todooit.db` |
| CSS cache | `~/.cache/todooit` |
| Config | `~/.config/todooit/config.py` |

`todooit config-loc` prints the config path on your machine.

Nothing here touches a dooit install — todooit has its own directories.
todooit uses a different database schema than dooit, so it can't open a dooit
database directly. [Migrate it](#migrating-from-dooit) once instead.

## One self-contained instance

Set `TODOOIT_HOME` and all three move into that one directory:

```
$TODOOIT_HOME/
    todooit.db
    cache/
    config.py
```

```bash
TODOOIT_HOME=~/scratch/todooit todooit
```

`todooit --dev` is the same thing pointed at the platform data directory for
`todooit-dev` — handy for trying config changes next to a running instance
without touching your real todos.

## The database

SQLite through SQLAlchemy. The schema, indexes included, is created from the
models on first connect. Existing tables are never altered, so there are no
migrations between todooit versions: a database has to match the current
schema. The one exception is a dooit database,
[migrated once](#migrating-from-dooit) into a new file.

::: tip Writing to the database from outside
The app reads the database when it starts and does not watch it afterwards.
Rows written by another process while it is running (a script using
`todooit.api`, a second todooit) show up after a restart.
:::

## Migrating from dooit

`migration/db_migration.py` copies a [dooit](https://github.com/dooit-org/dooit)
v3 database into a new todooit database. Run it from a checkout of the repo:

```bash
uv run python migration/db_migration.py                     # dooit's own ~/.local/share/dooit/dooit.db
uv run python migration/db_migration.py path/to/dooit.db    # any other dooit database
uv run python migration/db_migration.py --dry-run           # report only, write nothing
```

It writes the database todooit opens: `$TODOOIT_HOME/todooit.db` when
`TODOOIT_HOME` is set, otherwise `~/.local/share/todooit/todooit.db`. To try a
migration without touching your real todos, point it at a separate instance:

```bash
TODOOIT_HOME=~/scratch/todooit uv run python migration/db_migration.py
TODOOIT_HOME=~/scratch/todooit todooit
```

**Safety**

- The dooit database is opened read-only and never changed.
- If a todooit database already exists, the script refuses to run. With
  `--force` it moves the existing file aside to `todooit.db.bak-<timestamp>`
  in the same directory, then writes the new one.
- The new database is built in a temporary file and only renamed into place
  once it's complete, so a failed run leaves nothing behind.
- Only dooit v3 databases are accepted (v3.0 to v3.3.4, the latest release,
  share one schema).
  Anything else, including a todooit database, is rejected without writing
  anything.

**What carries over**

| dooit | todooit |
| --- | --- |
| workspaces | projects, with the same tree, names and order |
| todos and their steps | todos and steps, with the same descriptions, order and status |
| urgency 1 / 2 / 3 / 4 | priority none / p3 / p2 / p1 |
| due date | due date |
| recurrence | a cadence (`3d`, `2w`, `5h`); the todo's due date becomes its scheduled date, since a recurring todo has no due date |

**What is fitted**

dooit let every todo hold any value; todooit keeps a task and its steps
consistent (see [Steps](/guide/tasks#steps)). So each tree is fitted the way
the app fits a task filed under another, and the summary counts every change:

- A completed todo's open steps are completed with it.
- A step stops recurring when a todo above it recurs, has a due date or is
  completed — only one todo on a family line repeats. Its dooit due date stays
  its due date.
- An open step due after a todo above it takes that todo's due date.

**What doesn't**

- **Effort** has no todooit equivalent and is dropped. The summary counts how
  many todos had one.
- **Recurrence in minutes.** dooit's `m` meant minutes. todooit has no minutes,
  and its `m` is a month. An interval that isn't a whole number of hours is
  rounded up to whole hours (at least `1h`), and the script prints a warning
  naming each todo it changed.
- **Completion dates.** dooit never recorded when a todo was completed, so
  completed todos have none and sort last in Completed.
- **Tags** were words starting with `@` in the description; they stay in the
  description as plain words.

## Backing up

The database is one file. Copy it.

```bash
cp ~/.local/share/todooit/todooit.db ~/todooit-backup.db
```

todooit makes one backup itself. Notes are stored as markdown, and the first
start on a database from before that copies it to a `backups` folder beside it
(`~/.local/share/todooit/backups/`) and then converts every note, once and one
way. If the copy fails, todooit stops with an error and changes nothing.
