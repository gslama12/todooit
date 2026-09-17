"""
The change detection the db poller runs on

Dooit polls the database file's mtime once a second and refreshes every pane
when it moves — that is how an edit made in a second dooit (or straight in
the database) shows up in a running one.
"""

import os
import sqlite3
import tempfile
from pathlib import Path

from todooit.api import Project, manager
from todooit.utils.database import INDEXES

# Read off the migration rather than written out again: the point of the
# tests below is that the models and the migration agree, and a list copied
# by hand would only say that this file agrees with itself.
EXPECTED_INDEXES = [
    statement.split(" ON ")[0].rsplit(" ", 1)[-1] for statement in INDEXES
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
    """The indexes dooit laid down, as the database itself reports them"""

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


def test_a_database_written_before_the_indexes_gets_them():
    """
    The case `create_all` cannot answer on its own

    `create_all` skips a table it already found, indexes and all, so a
    database from before these existed would keep none of them however they
    are declared on the models. Connecting is what puts them there.
    """

    with tempfile.TemporaryDirectory() as folder:
        db = Path(folder) / "todooit.db"

        # A database with the tables but none of the indexes, which is what
        # every database written before them looks like
        manager.connect(str(db))
        Project(description="test").save()

        connection = sqlite3.connect(db)
        for name in _index_names(db):
            connection.execute(f"DROP INDEX {name}")
        connection.commit()
        connection.close()

        assert _index_names(db) == set()

        manager.session.close()
        manager.engine.dispose()

        manager.connect(str(db))
        assert _index_names(db) == set(EXPECTED_INDEXES)

        # And the rows that were already there are still there
        assert [p.description for p in Project.all()] == ["test"]

        manager.session.close()
        manager.engine.dispose()


def test_connecting_twice_does_not_double_the_indexes():
    """Every launch runs the migration; the second one must be a no-op"""

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
