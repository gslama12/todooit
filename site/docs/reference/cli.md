# CLI

```
todooit [OPTIONS] [COMMAND]
```

With no command, todooit starts the app.

## Options

| Option | What it does |
| --- | --- |
| `-v`, `--version` | Print the version and exit |
| `-c`, `--config PATH` | Load this config file instead of the default location |
| `--db PATH` | Use this SQLite file instead of the default database |
| `--dev` | Run an isolated dev instance (own database, cache and config) |
| `-h`, `--help` | Show help |

`--config` pointing at a file that does not exist prints a message and exits
without starting the app.

`--dev` is shorthand for setting `TODOOIT_HOME` to the platform data directory
for `todooit-dev`. An explicit `TODOOIT_HOME` always wins over it.

## Commands

### `config-loc`

```bash
todooit config-loc
```

Prints where todooit looks for your config file.

## Environment

| Variable | What it does |
| --- | --- |
| `TODOOIT_HOME` | Put the database, cache and config in this one directory |

See [Data & files](/reference/data).
