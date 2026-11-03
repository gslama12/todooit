"""
What connecting lays down in a database: the schema's indexes, once, minus retired columns
"""

import sqlite3
import tempfile
from pathlib import Path

from todooit.api import manager

# The indexes the models declare, and so the ones `create_all` lays down
EXPECTED_INDEXES = [
    "ix_todo_parent_todo_id",
    "ix_todo_parent_project_id",
    "ix_project_parent_project_id",
    "ix_todo_pending_scheduled",
    "ix_todo_binned_at",
]


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


def _todo_columns(db: Path) -> set:
    connection = sqlite3.connect(db)

    try:
        return {row[1] for row in connection.execute("PRAGMA table_info(todo)")}
    finally:
        connection.close()


def test_connecting_drops_the_retired_agent_column():
    """A database from before the agent flag was removed loses its column"""

    with tempfile.TemporaryDirectory() as folder:
        db = Path(folder) / "todooit.db"

        manager.connect(str(db))
        manager.session.close()
        manager.engine.dispose()

        connection = sqlite3.connect(db)
        connection.execute("ALTER TABLE todo ADD COLUMN agent BOOLEAN NOT NULL DEFAULT 0")
        connection.commit()
        connection.close()
        assert "agent" in _todo_columns(db)

        manager.connect(str(db))
        assert "agent" not in _todo_columns(db)

        manager.session.close()
        manager.engine.dispose()
