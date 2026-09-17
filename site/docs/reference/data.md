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

SQLite through SQLAlchemy. The schema is created on first connect, and older
databases are migrated in place on startup: columns that were added later
(`scheduled`, `note`, `completed_at`, the agent flag, the Bin columns, project
color) are bolted on when they are missing, and the indexes are laid after.

::: tip Two todooits on one database
The app polls the database file's modification time once a second. A write
from somewhere else is picked up and every pane redrawn. Those rows are not
treated as a change made here, so `ctrl+z` will not take them back.
:::

## Backing up

The database is one file. Copy it.

```bash
cp ~/.local/share/todooit/todooit.db ~/todooit-backup.db
```
