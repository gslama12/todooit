"""
Migrating a dooit v3 database: what carries over, and what is never touched
"""

import hashlib
import os
import sqlite3
import subprocess
import sys
from datetime import datetime, timedelta
from pathlib import Path

import pytest
from platformdirs import user_data_dir

from migration import db_migration
from migration.db_migration import MigrationError, migrate
from tests.test_core.test_sync import EXPECTED_INDEXES, _index_names
from todooit.api import Project, Todo, manager
from todooit.api.cadence import EPOCH, Cadence
from todooit.paths import HOME_ENV_VAR, database_file

REPO = Path(__file__).parents[2]
DOOIT_DDL = Path(__file__).with_name("dooit_v3.sql")

DUE = "2026-03-04 09:30:00.000000"


# --------------------------------------------------------------------------
# Never the live database


def _fingerprint(path: Path):
    if not path.exists():
        return None

    stat = path.stat()
    return stat.st_size, stat.st_mtime_ns


@pytest.fixture(autouse=True, scope="module")
def default_db(tmp_path_factory):
    """
    A stand-in at the path the live database has when TODOOIT_HOME is unset

    Checked in place of the real file, which a running todooit writes to at any
    moment, and which a migration going to the wrong place then cannot reach.
    """

    sandbox = tmp_path_factory.mktemp("default_location")

    with pytest.MonkeyPatch.context() as patch:
        # platformdirs goes by XDG_DATA_HOME on Linux and by HOME on macOS
        patch.setenv("XDG_DATA_HOME", str(sandbox))
        patch.setenv("HOME", str(sandbox))

        path = Path(user_data_dir("todooit")) / "todooit.db"
        assert path.is_relative_to(sandbox)

        path.parent.mkdir(parents=True)
        path.write_bytes(b"not to be touched")

        before = _fingerprint(path)
        yield path
        assert _fingerprint(path) == before


@pytest.fixture(autouse=True)
def home(monkeypatch, tmp_path, default_db):
    """Every target these tests write is under pytest's temp dir"""

    monkeypatch.setenv(HOME_ENV_VAR, str(tmp_path / "home"))

    assert database_file().is_relative_to(tmp_path)
    assert database_file() != default_db

    return tmp_path / "home"


# --------------------------------------------------------------------------
# Building dooit databases


def interval(td: timedelta) -> str:
    """A timedelta as dooit's Interval column stored it"""

    return (EPOCH + td).strftime("%Y-%m-%d %H:%M:%S.%f")


def workspace(id, parent=None, description="", order_index=0, is_root=False):
    return dict(
        id=id,
        order_index=order_index,
        description=description,
        is_root=is_root,
        parent_workspace_id=parent,
    )


def todo(id, workspace=None, parent_todo=None, description="", **fields):
    row = dict(
        id=id,
        order_index=0,
        description=description,
        due=None,
        effort=0,
        recurrence=None,
        urgency=1,
        pending=True,
        parent_workspace_id=workspace,
        parent_todo_id=parent_todo,
    )
    row.update(fields)
    return row


def build_dooit(path: Path, workspaces=(), todos=()) -> Path:
    connection = sqlite3.connect(path)

    with connection:
        connection.executescript(DOOIT_DDL.read_text())

        for table, rows in (("workspace", workspaces), ("todo", todos)):
            for row in rows:
                connection.execute(
                    f"INSERT INTO {table} ({', '.join(row)}) "
                    f"VALUES ({', '.join('?' * len(row))})",
                    list(row.values()),
                )

    connection.close()
    return path


@pytest.fixture
def source(tmp_path):
    """A small dooit database: root, a workspace with a child, a todo with a step"""

    return build_dooit(
        tmp_path / "dooit.db",
        workspaces=[
            workspace(1, is_root=True),
            workspace(2, parent=1, description="work", order_index=0),
            workspace(3, parent=2, description="meetings", order_index=0),
            workspace(4, parent=1, description="home", order_index=1),
        ],
        todos=[
            todo(1, workspace=2, description="write report", due=DUE, urgency=4),
            todo(2, parent_todo=1, description="outline", pending=False),
            todo(3, workspace=4, description="water plants", due=DUE, recurrence=interval(timedelta(days=3))),
        ],
    )


def rows(db: Path, table: str):
    connection = sqlite3.connect(db)
    connection.row_factory = sqlite3.Row

    try:
        return {
            row["id"]: dict(row)
            for row in connection.execute(f"SELECT * FROM {table}")
        }
    finally:
        connection.close()


def migrate_one(tmp_path, **fields) -> dict:
    """Migrate one todo and return its todooit row"""

    db = build_dooit(
        tmp_path / "one.db",
        workspaces=[workspace(1, is_root=True), workspace(2, parent=1)],
        todos=[todo(1, workspace=2, **fields)],
    )
    migrate(db, database_file())

    return rows(database_file(), "todo")[1]


def sha(path: Path) -> str:
    return hashlib.sha256(path.read_bytes()).hexdigest()


# --------------------------------------------------------------------------
# What carries over


def test_workspaces_become_projects(source):
    migrate(source, database_file())

    projects = rows(database_file(), "project")

    assert {id: p["parent_project_id"] for id, p in projects.items()} == {
        1: None,
        2: 1,
        3: 2,
        4: 1,
    }
    assert projects[1]["is_root"] == 1
    assert projects[4]["description"] == "home"
    assert projects[4]["order_index"] == 1
    assert all(p["color"] is None for p in projects.values())


def test_todos_keep_their_place(source):
    migrate(source, database_file())

    todos = rows(database_file(), "todo")

    assert todos[1]["parent_project_id"] == 2
    assert todos[2]["parent_todo_id"] == 1
    assert todos[2]["parent_project_id"] is None
    assert todos[1]["description"] == "write report"


@pytest.mark.parametrize(
    "urgency, priority",
    [(1, 0), (2, 3), (3, 2), (4, 1), (0, 0)],
)
def test_urgency_becomes_priority(tmp_path, urgency, priority):
    assert migrate_one(tmp_path, urgency=urgency)["priority"] == priority


def test_a_plain_todo_keeps_its_due_date_and_status(tmp_path):
    row = migrate_one(tmp_path, due=DUE, pending=False)

    assert (row["due"], row["scheduled"], row["pending"]) == (DUE, None, 0)
    assert row["completed_at"] is None
    assert row["recurrence"] is None


def test_new_columns_get_todooit_defaults(tmp_path):
    row = migrate_one(tmp_path)

    assert row["binned_at"] is None
    assert (row["origin_path"], row["note"], row["attachments"]) == ("", "", "")


def test_effort_is_dropped_and_counted(tmp_path):
    db = build_dooit(
        tmp_path / "effort.db",
        workspaces=[workspace(1, is_root=True)],
        todos=[todo(1, workspace=1, effort=3), todo(2, workspace=1)],
    )

    report = migrate(db, database_file())

    assert report.effort_dropped == 1
    assert "effort" not in rows(database_file(), "todo")[1]


@pytest.mark.parametrize(
    "every, cadence",
    [
        (timedelta(days=1), "1d"),
        (timedelta(days=3), "3d"),
        (timedelta(weeks=2), "2w"),
        (timedelta(hours=5), "5h"),
        (timedelta(days=1, hours=2), "26h"),
    ],
)
def test_recurrence_becomes_cadence_text(tmp_path, every, cadence):
    assert migrate_one(tmp_path, recurrence=interval(every))["recurrence"] == cadence


@pytest.mark.parametrize(
    "every, cadence",
    [
        (timedelta(minutes=30), "1h"),
        (timedelta(minutes=90), "2h"),
        (timedelta(days=1, minutes=1), "25h"),
    ],
)
def test_minute_recurrence_is_rounded_up_to_hours(tmp_path, every, cadence):
    """dooit's `30m` was minutes; todooit would read it as 30 months"""

    db = build_dooit(
        tmp_path / "minutes.db",
        workspaces=[workspace(1, is_root=True)],
        todos=[todo(1, workspace=1, description="stretch", recurrence=interval(every))],
    )

    report = migrate(db, database_file())

    assert rows(database_file(), "todo")[1]["recurrence"] == cadence
    assert report.recurrence_changed == [(1, "stretch", every, cadence)]
    assert any("stretch" in line and cadence in line for line in report.lines())


def test_a_zero_recurrence_is_dropped_with_a_warning(tmp_path):
    db = build_dooit(
        tmp_path / "zero.db",
        workspaces=[workspace(1, is_root=True)],
        todos=[todo(1, workspace=1, due=DUE, recurrence=interval(timedelta(0)))],
    )

    report = migrate(db, database_file())
    row = rows(database_file(), "todo")[1]

    assert row["recurrence"] is None
    assert row["due"] == DUE
    assert report.recurrence_changed[0][3] is None


def test_a_recurring_todo_is_scheduled_not_due(tmp_path):
    row = migrate_one(
        tmp_path, due=DUE, pending=False, recurrence=interval(timedelta(days=7))
    )

    assert (row["due"], row["scheduled"], row["pending"]) == (None, DUE, 1)


def test_the_result_opens_in_todooit(source):
    """Read back through the models: the schema and every value are what the app expects"""

    migrate(source, database_file())

    manager.connect(str(database_file()))

    try:
        report = manager.session.get(Todo, 1)
        plants = manager.session.get(Todo, 3)

        assert report.priority == 1
        assert report.parent_project.description == "work"
        assert [t.description for t in report.todos] == ["outline"]
        assert plants.recurrence == Cadence(3, "days")
        assert plants.scheduled == datetime(2026, 3, 4, 9, 30)
        assert manager.session.get(Project, 3).parent_project.description == "work"
    finally:
        manager.session.close()
        manager.engine.dispose()

    assert _index_names(database_file()) == set(EXPECTED_INDEXES)


def test_the_report_counts_what_moved(source):
    report = migrate(source, database_file())

    assert (report.projects, report.todos, report.recurring) == (4, 3, 1)
    assert str(source) in report.lines()[0]
    assert str(database_file()) in report.lines()[1]


# --------------------------------------------------------------------------
# What is never touched


def test_the_dooit_database_is_unchanged(source):
    before = sha(source)

    migrate(source, database_file())

    assert sha(source) == before


def test_an_existing_target_is_refused_without_force(source):
    database_file().parent.mkdir(parents=True)
    database_file().write_bytes(b"precious")

    with pytest.raises(MigrationError, match="--force"):
        migrate(source, database_file())

    assert database_file().read_bytes() == b"precious"


def test_force_backs_up_the_existing_target(source):
    database_file().parent.mkdir(parents=True)
    database_file().write_bytes(b"precious")

    report = migrate(source, database_file(), force=True)

    assert report.backup.read_bytes() == b"precious"
    assert report.backup.parent == database_file().parent
    assert report.backup.name.startswith("todooit.db.bak-")
    assert 2 in rows(database_file(), "project")


def test_a_dry_run_writes_nothing(source, home):
    report = migrate(source, database_file(), dry_run=True)

    assert report.todos == 3
    assert not home.exists()
    assert "nothing was written" in report.lines()[-1]


def test_a_dry_run_says_an_existing_target_needs_force(source):
    database_file().parent.mkdir(parents=True)
    database_file().write_bytes(b"precious")

    report = migrate(source, database_file(), dry_run=True)

    assert any("--force" in line for line in report.lines())
    assert database_file().read_bytes() == b"precious"


def test_a_failed_write_leaves_nothing_behind(source, monkeypatch):
    database_file().parent.mkdir(parents=True)
    database_file().write_bytes(b"precious")

    def fail(*args):
        raise sqlite3.OperationalError("disk full")

    monkeypatch.setattr(db_migration, "_insert", fail)

    with pytest.raises(sqlite3.OperationalError):
        migrate(source, database_file(), force=True)

    assert database_file().read_bytes() == b"precious"
    assert os.listdir(database_file().parent) == ["todooit.db"]


# --------------------------------------------------------------------------
# What is refused


def test_a_missing_source_is_refused(tmp_path):
    with pytest.raises(MigrationError, match="no dooit database"):
        migrate(tmp_path / "nowhere.db", database_file())


def test_a_file_that_is_not_sqlite_is_refused(tmp_path):
    junk = tmp_path / "junk.db"
    junk.write_text("not a database")

    with pytest.raises(MigrationError, match="SQLite"):
        migrate(junk, database_file())


def test_a_todooit_database_is_refused(tmp_path):
    db = tmp_path / "todooit.db"
    manager.connect(str(db))
    manager.session.close()
    manager.engine.dispose()

    with pytest.raises(MigrationError, match="already a todooit database"):
        migrate(db, database_file())


def test_an_unknown_schema_is_refused(tmp_path):
    db = tmp_path / "other.db"
    connection = sqlite3.connect(db)
    connection.executescript(DOOIT_DDL.read_text())
    connection.execute("ALTER TABLE todo ADD COLUMN tags VARCHAR")
    connection.close()

    with pytest.raises(MigrationError, match="not a dooit v3 database"):
        migrate(db, database_file())


def test_a_todo_without_a_parent_is_refused(tmp_path):
    db = build_dooit(
        tmp_path / "orphan.db",
        workspaces=[workspace(1, is_root=True)],
        todos=[todo(1, description="lost")],
    )

    with pytest.raises(MigrationError, match="0 parents"):
        migrate(db, database_file())

    assert not database_file().exists()


def test_migrating_onto_the_source_is_refused(source):
    with pytest.raises(MigrationError, match="same file"):
        migrate(source, source, force=True)


# --------------------------------------------------------------------------
# The script


def run_script(home: Path, *args):
    return subprocess.run(
        [sys.executable, str(REPO / "migration" / "db_migration.py"), *map(str, args)],
        env={**os.environ, HOME_ENV_VAR: str(home)},
        capture_output=True,
        text=True,
    )


def test_the_script_migrates_into_todooit_home(source, home):
    done = run_script(home, source)

    assert done.returncode == 0, done.stderr
    assert f"target: {home / 'todooit.db'}" in done.stdout
    assert 2 in rows(home / "todooit.db", "project")

    again = run_script(home, source)

    assert again.returncode == 1
    assert "--force" in again.stderr

    forced = run_script(home, source, "--force")

    assert forced.returncode == 0, forced.stderr
    assert "backup" in forced.stdout
