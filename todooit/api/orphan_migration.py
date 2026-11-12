"""
The one-time move of completed orphans to the Bin

Completed tasks used to live in a global Completed pane, so dropping a project
left its completed tasks there with no project. Completed tasks now stay in
their project, and an orphan is always binned: a completed orphan that isn't
binned yet goes to the Bin, steps and all, keeping its `origin_path` so a
restore rebuilds its project. `PRAGMA user_version` is the marker that it's
done; the move itself finds nothing the second time, so it is idempotent too.
"""

from datetime import datetime

from sqlalchemy.engine import Engine

from .note_migration import MARKDOWN_NOTES_VERSION

# After the notes, which set the version to theirs
BINNED_ORPHANS_VERSION = MARKDOWN_NOTES_VERSION + 1

# How SQLAlchemy writes a datetime into SQLite, so the stamp reads back as one
STAMP_FORMAT = "%Y-%m-%d %H:%M:%S.%f"

# The orphans' whole families, so no step is left behind outside the Bin
BIN_ORPHANS = """
WITH RECURSIVE family(id) AS (
    SELECT id FROM todo
    WHERE pending = 0
      AND binned_at IS NULL
      AND parent_project_id IS NULL
      AND parent_todo_id IS NULL
    UNION ALL
    SELECT todo.id FROM todo JOIN family ON todo.parent_todo_id = family.id
)
UPDATE todo SET binned_at = ? WHERE id IN family AND binned_at IS NULL
"""


def orphans_due(engine: Engine) -> bool:
    with engine.connect() as connection:
        version = connection.exec_driver_sql("PRAGMA user_version").scalar()

    return (version or 0) < BINNED_ORPHANS_VERSION


def bin_completed_orphans(engine: Engine) -> None:
    """Bin every completed orphan under one stamp and set the marker, all or nothing."""

    with engine.begin() as connection:
        connection.exec_driver_sql(BIN_ORPHANS, (datetime.now().strftime(STAMP_FORMAT),))
        connection.exec_driver_sql(f"PRAGMA user_version = {BINNED_ORPHANS_VERSION}")
