"""
The one-time move of completed orphans to the Bin, when a database is opened

A completed task whose project was dropped while it sat in the old Completed
pane has no project and isn't binned. Opening the database bins it, steps and
all, keeping its origin path; once, and harmlessly again.
"""

from pathlib import Path

import pytest

from tests.test_core.core_base import *  # noqa
from todooit.api import BIN, Project, Todo, manager, restore_todo
from todooit.api.orphan_migration import (
    BINNED_ORPHANS_VERSION,
    bin_completed_orphans,
    orphans_due,
)


def user_version() -> int:
    with manager.engine.connect() as connection:
        return connection.exec_driver_sql("PRAGMA user_version").scalar() or 0


def set_user_version(version: int) -> None:
    with manager.engine.begin() as connection:
        connection.exec_driver_sql(f"PRAGMA user_version = {version}")


@pytest.fixture
def old_database(tmp_path: Path):
    """
    A database as the Completed pane left it: a completed orphan with a step,
    beside an open task, a binned completed one and a completed one at home
    """

    path = str(tmp_path / "todooit.db")
    manager.connect(path)

    home = Project(description="home")
    home.save()

    orphan = Todo(description="orphan", parent_project=home)
    orphan.save()
    Todo(description="orphan step", parent_todo=orphan).save()
    orphan.toggle_complete()

    Todo(description="open", parent_project=home).save()

    done_at_home = Todo(description="done at home", parent_project=home)
    done_at_home.save()
    done_at_home.toggle_complete()

    binned = Todo(description="binned", parent_project=home)
    binned.save()
    binned.toggle_complete()
    binned.origin_path = "gone"
    binned.parent_project = None
    binned.binned_at = binned.completed_at
    binned.save()

    # Its project was dropped while it sat in Completed
    orphan.origin_path = "garden"
    orphan.parent_project = None
    orphan.save()

    set_user_version(BINNED_ORPHANS_VERSION - 1)
    manager.session.close()

    yield path

    manager.session.close()


def by_description() -> dict:
    return {todo.description: todo for todo in Todo.all()}


def test_opening_bins_completed_orphans_with_their_steps(old_database):
    binned_before = by_description()["binned"].binned_at
    manager.session.close()

    manager.connect(old_database)
    todos = by_description()

    assert todos["orphan"].is_binned
    assert todos["orphan step"].is_binned
    assert todos["orphan"].origin_path == "garden"
    assert todos["orphan"] in BIN.todos

    # Everything that already had a home is left as it was
    assert not todos["open"].is_binned
    assert not todos["done at home"].is_binned
    assert todos["binned"].binned_at == binned_before

    assert user_version() == BINNED_ORPHANS_VERSION
    assert not orphans_due(manager.engine)


def test_the_move_is_idempotent(old_database):
    manager.connect(old_database)
    stamps = {t.description: t.binned_at for t in Todo.all()}

    bin_completed_orphans(manager.engine)
    manager.session.expire_all()

    assert {t.description: t.binned_at for t in Todo.all()} == stamps


def test_a_migrated_orphan_restores_into_its_rebuilt_project(old_database):
    manager.connect(old_database)
    orphan = by_description()["orphan"]

    (rebuilt,) = restore_todo(orphan)

    assert rebuilt.description == "revived - garden"
    assert orphan.parent_project is rebuilt
    assert orphan.is_completed


def test_a_new_database_is_already_up_to_date(tmp_path: Path):
    manager.connect(str(tmp_path / "new.db"))

    assert user_version() == BINNED_ORPHANS_VERSION
