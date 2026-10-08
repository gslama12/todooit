"""
Migrate a dooit v3 database into todooit

    uv run python migration/db_migration.py [DOOIT_DB] [--force] [--dry-run]

Reads DOOIT_DB (default: dooit's own ~/.local/share/dooit/dooit.db) without
modifying it, and writes the database todooit opens: the one under
TODOOIT_HOME when that is set, otherwise the live ~/.local/share/todooit.
An existing todooit database is only replaced with --force, and is then kept
as todooit.db.bak-<timestamp> beside it.

dooit (https://github.com/dooit-org/dooit) is what todooit was forked from.
Its v3 schema is two tables, `workspace` and `todo`, unchanged across every
3.x release. todooit renamed workspaces to projects, turned dooit's 1-4
urgency into a 0-3 priority, dropped `effort`, stores recurrence as typed text
and added a column or five. This copies a dooit database's rows into a fresh
todooit database built from todooit's own models, so the result always matches
the schema the app expects.

The dooit file is only ever opened read-only. The todooit file is written to a
temporary file beside the target and renamed into place once complete, so a
failed run leaves nothing behind; an existing target is refused unless forced,
and then moved aside to a timestamped backup rather than overwritten.

What cannot carry over:

- `effort` has no todooit column and is dropped.
- dooit's `m` recurrence meant minutes; todooit has none (its `m` is a month),
  so an interval that is not whole hours is rounded up to whole hours.
- dooit never recorded when a todo was completed, so `completed_at` is empty.
"""

import argparse
import math
import os
import sqlite3
import sys
from dataclasses import dataclass, field
from datetime import datetime, timedelta
from pathlib import Path
from typing import List, Optional, Tuple

from platformdirs import user_data_dir

from todooit.api.cadence import EPOCH, Cadence
from todooit.paths import database_file

# Where dooit v3 keeps its database
DOOIT_DB = Path(user_data_dir("dooit")) / "dooit.db"

# The dooit v3 schema, as every 3.x release created it
DOOIT_COLUMNS = {
    "workspace": {"id", "order_index", "description", "is_root", "parent_workspace_id"},
    "todo": {
        "id",
        "order_index",
        "description",
        "due",
        "effort",
        "recurrence",
        "urgency",
        "pending",
        "parent_workspace_id",
        "parent_todo_id",
    },
}

# dooit urgency 1 (none) .. 4 (most urgent) -> todooit priority 0 (none), 1 (highest) .. 3
URGENCY_TO_PRIORITY = {1: 0, 2: 3, 3: 2, 4: 1}


class MigrationError(Exception):
    """The migration refused to run; nothing was written"""


@dataclass
class Report:
    source: Path
    target: Path
    dry_run: bool
    target_exists: bool
    projects: int = 0
    todos: int = 0
    recurring: int = 0
    # Todos whose non-zero effort had nowhere to go
    effort_dropped: int = 0
    # (todo id, description, dooit interval, todooit cadence or None if dropped)
    recurrence_changed: List[Tuple[int, str, timedelta, Optional[str]]] = field(
        default_factory=list
    )
    backup: Optional[Path] = None

    def lines(self) -> List[str]:
        lines = [
            f"source: {self.source}",
            f"target: {self.target}",
            f"projects: {self.projects} (including the root)",
            f"todos: {self.todos} ({self.recurring} recurring)",
        ]

        if self.effort_dropped:
            lines.append(f"effort dropped: {self.effort_dropped} todo(s) had a non-zero effort")

        for todo_id, description, interval, cadence in self.recurrence_changed:
            change = f"rounded up to {cadence}" if cadence else "dropped"
            lines.append(
                f"warning: todo {todo_id} ({description!r}) recurred every "
                f"{interval}, which todooit cannot express; {change}"
            )

        if self.backup:
            lines.append(f"backup of the replaced database: {self.backup}")

        if self.dry_run:
            if self.target_exists:
                lines.append("dry run: the target exists, a real run needs --force")
            lines.append("dry run: nothing was written")

        return lines


def migrate(
    source: Path,
    target: Path,
    force: bool = False,
    dry_run: bool = False,
) -> Report:
    """Copy the dooit database at `source` into a new todooit database at `target`"""

    source, target = Path(source).expanduser(), Path(target).expanduser()

    if not source.is_file():
        raise MigrationError(f"no dooit database at {source}")

    if target.exists() and target.resolve() == source.resolve():
        raise MigrationError("source and target are the same file")

    workspaces, todo_rows = _read_dooit(source)

    report = Report(source, target, dry_run, target.exists())
    projects = [_project(row) for row in workspaces]
    todos = [_todo(row, report) for row in todo_rows]
    report.projects, report.todos = len(projects), len(todos)

    if dry_run:
        return report

    if report.target_exists and not force:
        raise MigrationError(
            f"{target} already exists; pass --force to replace it "
            "(it is kept as a timestamped backup)"
        )

    _write(target, projects, todos, report)

    return report


# --------------------------------------------------------------------------
# Reading dooit


def _read_dooit(source: Path) -> Tuple[List[sqlite3.Row], List[sqlite3.Row]]:
    connection = sqlite3.connect(f"{source.resolve().as_uri()}?mode=ro", uri=True)
    connection.row_factory = sqlite3.Row

    try:
        _check_schema(connection)

        workspaces = connection.execute("SELECT * FROM workspace ORDER BY id").fetchall()
        todos = connection.execute("SELECT * FROM todo ORDER BY id").fetchall()
    except sqlite3.DatabaseError as error:
        raise MigrationError(
            f"{source} is not a readable SQLite database: {error}"
        ) from error
    finally:
        connection.close()

    _check_parents(todos)

    return workspaces, todos


def _check_schema(connection: sqlite3.Connection):
    tables = {
        name
        for (name,) in connection.execute(
            "SELECT name FROM sqlite_master WHERE type = 'table'"
        )
    }

    if "project" in tables:
        raise MigrationError("this is already a todooit database")

    for table, expected in DOOIT_COLUMNS.items():
        if table not in tables:
            raise MigrationError(f"not a dooit v3 database: no `{table}` table")

        columns = {row[1] for row in connection.execute(f"PRAGMA table_info({table})")}

        if columns != expected:
            raise MigrationError(
                f"not a dooit v3 database: `{table}` has columns {sorted(columns)}, "
                f"expected {sorted(expected)}"
            )


def _check_parents(todos: List[sqlite3.Row]):
    """dooit held this too; a database breaking it was not written by dooit"""

    for row in todos:
        parents = (row["parent_workspace_id"] is not None) + (
            row["parent_todo_id"] is not None
        )

        if parents != 1:
            raise MigrationError(
                f"todo {row['id']} ({row['description']!r}) has {parents} parents, "
                "expected exactly one"
            )


# --------------------------------------------------------------------------
# Mapping rows


def _project(row: sqlite3.Row) -> dict:
    return {
        "id": row["id"],
        "order_index": row["order_index"],
        "description": row["description"],
        "is_root": row["is_root"],
        # No colors in dooit; a project without one inherits nothing
        "color": None,
        "parent_project_id": row["parent_workspace_id"],
    }


def _todo(row: sqlite3.Row, report: Report) -> dict:
    cadence = _cadence(row, report)
    due, scheduled, pending = row["due"], None, row["pending"]

    if cadence is not None:
        # A recurring todo is planned by its scheduled date and has no due date
        report.recurring += 1
        due, scheduled, pending = None, row["due"], 1

    if row["effort"]:
        report.effort_dropped += 1

    return {
        "id": row["id"],
        "order_index": row["order_index"],
        "description": row["description"],
        "due": due,
        "scheduled": scheduled,
        "agent": 0,
        "recurrence": cadence,
        "priority": URGENCY_TO_PRIORITY.get(row["urgency"], 0),
        "pending": pending,
        # dooit never recorded it
        "completed_at": None,
        "binned_at": None,
        "origin_path": "",
        "note": "",
        "attachments": "",
        "parent_project_id": row["parent_workspace_id"],
        "parent_todo_id": row["parent_todo_id"],
    }


def _cadence(row: sqlite3.Row, report: Report) -> Optional[str]:
    """
    dooit's recurrence as todooit cadence text

    dooit stored a timedelta the way SQLAlchemy's Interval does on SQLite: as
    the moment that long after the epoch.
    """

    if row["recurrence"] is None:
        return None

    interval = datetime.fromisoformat(str(row["recurrence"])) - EPOCH
    seconds = interval.total_seconds()

    if seconds <= 0:
        report.recurrence_changed.append((row["id"], row["description"], interval, None))
        return None

    if seconds % 3600 == 0:
        return str(Cadence.from_timedelta(interval))

    # Minutes: todooit has none, so the nearest it can do without repeating
    # more often than before
    cadence = str(Cadence(max(1, math.ceil(seconds / 3600)), "hours"))
    report.recurrence_changed.append((row["id"], row["description"], interval, cadence))

    return cadence


# --------------------------------------------------------------------------
# Writing todooit


def _write(target: Path, projects: List[dict], todos: List[dict], report: Report):
    from sqlalchemy import create_engine

    from todooit.api import BaseModel

    target.parent.mkdir(parents=True, exist_ok=True)
    temporary = target.with_name(f".{target.name}.migrating-{os.getpid()}")
    temporary.unlink(missing_ok=True)

    try:
        engine = create_engine(f"sqlite:///{temporary}")
        BaseModel.metadata.create_all(bind=engine)
        engine.dispose()

        connection = sqlite3.connect(temporary)

        try:
            with connection:
                _insert(connection, "project", projects)
                _insert(connection, "todo", todos)
        finally:
            connection.close()

        if report.target_exists:
            stamp = datetime.now().strftime("%Y%m%d-%H%M%S")
            report.backup = target.with_name(f"{target.name}.bak-{stamp}")
            os.replace(target, report.backup)

        os.replace(temporary, target)
    finally:
        temporary.unlink(missing_ok=True)


def _insert(connection: sqlite3.Connection, table: str, rows: List[dict]):
    if not rows:
        return

    columns = list(rows[0])
    connection.executemany(
        f"INSERT INTO {table} ({', '.join(columns)}) "
        f"VALUES ({', '.join(':' + column for column in columns)})",
        rows,
    )


# --------------------------------------------------------------------------
# The command line


def main(argv=None) -> int:
    parser = argparse.ArgumentParser(
        prog="db_migration",
        description="Migrate a dooit v3 database into todooit.",
    )
    parser.add_argument(
        "source",
        nargs="?",
        type=Path,
        default=DOOIT_DB,
        help=f"the dooit database to read (default: {DOOIT_DB})",
    )
    parser.add_argument(
        "--force",
        action="store_true",
        help="replace an existing todooit database (it is backed up first)",
    )
    parser.add_argument(
        "--dry-run",
        action="store_true",
        help="report what would be migrated without writing anything",
    )
    args = parser.parse_args(argv)

    try:
        report = migrate(args.source, database_file(), force=args.force, dry_run=args.dry_run)
    except MigrationError as error:
        print(f"error: {error}", file=sys.stderr)
        return 1

    print("\n".join(report.lines()))
    return 0


if __name__ == "__main__":
    sys.exit(main())
