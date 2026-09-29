"""
The change detection the db poller runs on

Todooit polls the database file's mtime once a second and refreshes every pane
when it moves — that is how an edit made in a second todooit (or straight in
the database) shows up in a running one.
"""

import os
import sqlite3
import tempfile
from pathlib import Path

from todooit.api import Project, manager

# The indexes the models declare, and so the ones `create_all` lays down
EXPECTED_INDEXES = [
    "ix_todo_parent_todo_id",
    "ix_todo_parent_project_id",
    "ix_project_parent_project_id",
    "ix_todo_pending_scheduled",
    "ix_todo_binned_at",
]


def test_has_changed_notices_an_outside_write():
    with tempfile.TemporaryDirectory() as folder:
        db = Path(folder) / "todooit.db"
        manager.connect(str(db))

        p = Project(description="test")
        p.save()

        # Our own writes keep the recorded mtime current, so nothing looks
        # like it changed underneath us
        assert not manager.has_changed()

        # An outside write moves the file's mtime; the poller must see it
        # exactly once, and then treat the new state as the known one
        outside = os.path.getmtime(db) + 10
        os.utime(db, (outside, outside))

        assert manager.has_changed()
        assert not manager.has_changed()

        manager.session.close()
        manager.engine.dispose()


def _index_names(db: Path) -> set:
    """The indexes todooit laid down, as the database itself reports them"""

    connection = sqlite3.connect(db)

    try:
        return {
            name
            for (name,) in connection.execute(
                "SELECT name FROM sqlite_master WHERE type = ?", ("index",)
            )
            if name.startswith("ix_")
        }
    finally:
        connection.close()


def test_a_fresh_database_is_indexed():
    with tempfile.TemporaryDirectory() as folder:
        db = Path(folder) / "todooit.db"
        manager.connect(str(db))

        assert _index_names(db) == set(EXPECTED_INDEXES)

        manager.session.close()
        manager.engine.dispose()


def test_connecting_twice_does_not_double_the_indexes():
    """Every launch runs `create_all`; the second one must be a no-op"""

    with tempfile.TemporaryDirectory() as folder:
        db = Path(folder) / "todooit.db"

        manager.connect(str(db))
        first = _index_names(db)
        manager.session.close()
        manager.engine.dispose()

        manager.connect(str(db))
        assert _index_names(db) == first

        manager.session.close()
        manager.engine.dispose()
