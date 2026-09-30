"""
Undo/redo by row diffing

After each key press the project and todo tables are compared with the last
snapshot, and the rows that differ are recorded before and after. Undo writes
the old rows back, redo the new ones, so no edit needs a hand-written inverse.
Nothing is read unless `manager.revision` moved, so cursor keys cost nothing.
"""

from dataclasses import dataclass, field
from typing import Any, Dict, List, Optional

from sqlalchemy import delete, event, insert, select

from .manager import manager
from .project import Project
from .todo import Todo

# Notes are excluded from snapshots: they are large and the note editor has its
# own undo. Undo must still never lose one, so rewritten rows keep their
# current note and deleted rows get theirs back (see `_notes_of_deleted`).
NOTE = "note"

# Parents before children: rows are inserted in this order, deleted in reverse
TABLES = (Project, Todo)

MAX_DEPTH = 200

# One row of one table, keyed by column name
Row = Dict[str, Any]

# Rows of one table by id; None means the row did not exist on that side
TableRows = Dict[int, Optional[Row]]

# TableRows per table name
Fragment = Dict[str, TableRows]

# Every row of every table at one moment
Snapshot = Dict[str, Dict[int, Row]]


def _capture() -> Snapshot:
    """
    Every row of both tables, read via the tables (not the models, so no validators run)

    Skips the root project (created lazily; undoing it would drop the tree)
    and the note column.
    """

    snapshot: Snapshot = {}

    for model in TABLES:
        table = model.__table__
        columns = [column for column in table.c if column.name != NOTE]
        query = select(*columns)

        if model is Project:
            query = query.where(table.c.is_root == False)

        rows = manager.session.execute(query).mappings().all()
        snapshot[table.name] = {row["id"]: dict(row) for row in rows}

    return snapshot


# Notes of todos deleted since the last record, so undoing the delete restores them
_notes_of_deleted: Dict[int, str] = {}


@event.listens_for(Todo, "before_delete")
def _remember_note(_mapper, _connection, target: Todo) -> None:
    note = getattr(target, NOTE, "")

    if note:
        _notes_of_deleted[target.id] = note


@dataclass
class Change:
    """
    The rows one key changed: `before` and `after` (None = row absent on that side)
    """

    before: Fragment
    after: Fragment


@dataclass
class Restored:
    """
    What one undo/redo step did, as row uuids
    """

    # removed from the database
    gone: List[str] = field(default_factory=list)
    # re-inserted after being absent
    back: List[str] = field(default_factory=list)
    # present both times, contents changed
    changed: List[str] = field(default_factory=list)

    @property
    def touched(self) -> List[str]:
        return self.back + self.changed

    def summary(self) -> str:
        """
        Counts for the status bar, e.g. "2 rows back, 1 row changed"
        """

        def rows(count: int, what: str) -> str:
            label = "row" if count == 1 else "rows"
            return f"{count} {label} {what}"

        counted = (
            (self.back, "back"),
            (self.gone, "dropped"),
            (self.changed, "changed"),
        )

        return ", ".join(rows(len(group), what) for group, what in counted if group)


def _diff(before: Snapshot, after: Snapshot) -> Optional[Change]:
    """
    The rows that differ between two snapshots, or None if nothing did
    """

    old: Fragment = {}
    new: Fragment = {}

    for model in TABLES:
        name = model.__tablename__
        was, now = before[name], after[name]

        ids = [_id for _id in set(was) | set(now) if was.get(_id) != now.get(_id)]

        if not ids:
            continue

        old[name] = {_id: was.get(_id) for _id in ids}
        new[name] = {_id: now.get(_id) for _id in ids}

        # Deleted todos: store their note on the side that puts them back
        if model is Todo:
            for _id, row in old[name].items():
                note = _notes_of_deleted.get(_id)

                if note and now.get(_id) is None and row is not None:
                    row[NOTE] = note

    if not old:
        return None

    return Change(before=old, after=new)


def _apply(fragment: Fragment, leaving: Fragment) -> Restored:
    """
    Write one side of a change over the database (delete all named rows, reinsert)

    `leaving` is the other side, used only to classify rows for `Restored`.
    """

    session = manager.session
    restored = Restored()

    # Current notes of rows about to be rewritten, read before deleting them
    todo_table = Todo.__table__
    todo_ids = list(fragment.get(Todo.__tablename__, {}))
    kept_notes: Dict[int, str] = {}

    if todo_ids:
        kept_notes = {
            row.id: row.note
            for row in session.execute(
                select(todo_table.c.id, todo_table.c.note).where(
                    todo_table.c.id.in_(todo_ids)
                )
            )
        }

    # Delete children first
    for model in reversed(TABLES):
        rows = fragment.get(model.__tablename__)

        if not rows:
            continue

        table = model.__table__
        session.execute(delete(table).where(table.c.id.in_(list(rows))))

    # Insert parents first
    for model in TABLES:
        rows = fragment.get(model.__tablename__)

        if not rows:
            continue

        values = [row for row in rows.values() if row is not None]

        # Keep the current note, or the one saved when the row was deleted
        if model is Todo:
            values = [
                {**row, NOTE: row.get(NOTE, kept_notes.get(row["id"], ""))}
                for row in values
            ]

        if values:
            session.execute(insert(model.__table__), values)

        was_there = leaving.get(model.__tablename__, {})

        for _id, row in rows.items():
            uuid = f"{model.__name__}_{_id}"

            if row is None:
                restored.gone.append(uuid)
            elif was_there.get(_id) is None:
                restored.back.append(uuid)
            else:
                restored.changed.append(uuid)

    manager.commit()

    # Every loaded model object is now stale
    session.expire_all()

    return restored


class History:
    """
    One app-wide undo/redo history covering both panes
    """

    def __init__(self) -> None:
        self._undo: List[Change] = []
        self._redo: List[Change] = []
        self._baseline: Optional[Snapshot] = None
        self._revision = -1

    @property
    def started(self) -> bool:
        return self._baseline is not None

    def start(self) -> None:
        """Take the current database as the starting point"""

        self._undo.clear()
        self._redo.clear()
        self._sync()

    def _sync(self) -> None:
        self._baseline = _capture()
        self._revision = manager.revision
        _notes_of_deleted.clear()

    def record(self) -> bool:
        """
        Record what the last key changed; returns whether anything did
        """

        if not self.started or manager.revision == self._revision:
            return False

        assert self._baseline is not None

        after = _capture()
        change = _diff(self._baseline, after)

        _notes_of_deleted.clear()

        self._baseline = after
        self._revision = manager.revision

        if change is None:
            return False

        self._undo.append(change)
        del self._undo[:-MAX_DEPTH]

        # A new change invalidates the redo stack
        self._redo.clear()

        return True

    def undo(self) -> Optional[Restored]:
        """
        Revert the last change; None if there is nothing to undo
        """

        return self._step(self._undo, self._redo, forward=False)

    def redo(self) -> Optional[Restored]:
        """
        Reapply the last undone change; None if there is nothing to redo
        """

        return self._step(self._redo, self._undo, forward=True)

    def _step(
        self,
        source: List[Change],
        target: List[Change],
        forward: bool,
    ) -> Optional[Restored]:
        if not source:
            return None

        change = source.pop()
        wanted, leaving = (
            (change.after, change.before) if forward else (change.before, change.after)
        )

        restored = _apply(wanted, leaving)
        target.append(change)

        # The step itself isn't a change to record
        self._sync()

        return restored
