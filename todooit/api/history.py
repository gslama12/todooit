"""
Taking back what the panes just did, and putting it back again

Undo here is not a list of keys played backwards. A single key can change a
great deal at once — binning a project files every task in it somewhere else,
a sort renumbers every run in the database, ticking off a recurring todo hands
it back pending with a new date — and an inverse written by hand for each of
them is a second implementation of every edit in the app, kept in step with
the first by nothing but care.

So the rows are what is kept instead. After each key the two tables the panes
are drawn from are read and compared with how they were, and the rows that
differ are written down both ways round: what they held, and what they hold.
Undo puts the old rows back, redo puts the new ones back, and neither of them
has to know which key it is undoing. An edit nobody thought about here is
still taken back correctly, because what it did to the rows is all that was
ever recorded.

A change costs the rows it touched rather than the database it walked to find
them, and nothing at all is read while nothing is being written — a key that
only moves the cursor is two numbers compared.
"""

from dataclasses import dataclass, field
from typing import Any, Dict, List, Optional

from sqlalchemy import delete, event, insert, select

from .manager import manager
from .project import Project
from .todo import Todo

# The one field the history does not keep, and the reason it does not.
#
# A note is the only thing on a row that has no length worth speaking of, and
# it is read here more often than anything else in the app: every key that
# writes reads both tables to see what it changed. Counting the notes in makes
# that cost the size of everything ever written down rather than the number of
# rows, and makes the baseline the history holds a second copy of the whole
# database in memory.
#
# So notes sit outside undo. `ctrl+z` no longer takes back what was typed into
# a note -- the note window has its own undo on the same key, which is where
# writing is actually done -- and no change ever puts a note back to an older
# version of itself. What undo must still never do is *lose* one, and there
# are two ways it could: rewriting a row would blank the note the row is
# carrying, and restoring a deleted row would bring it back empty. Both are
# answered below, so nothing typed into a note is ever destroyed by a key
# pressed somewhere else.
NOTE = "note"

# The tables the panes are drawn from, parents before children. Rows are put
# back in this order and taken out in the reverse of it, so a project is never
# briefly filed under one that is not there yet, nor left behind by the todos
# that point at it.
TABLES = (Project, Todo)

# How many changes are kept. Each one holds only the rows it touched, so the
# depth is paid for in edits rather than in the size of the database: far
# enough back to walk out of a wrong turn, and well short of a whole session.
MAX_DEPTH = 200

# One row of one table, keyed by column name
Row = Dict[str, Any]

# The rows of one table as one side of a change found them, keyed by id. None
# stands for a row that was not there at all, which is what tells a row that
# was added apart from one that was merely edited.
TableRows = Dict[int, Optional[Row]]

# Those, per table: one side of a change, or of a step being applied
Fragment = Dict[str, TableRows]

# Every row of both tables, as the database holds them at one moment
Snapshot = Dict[str, Dict[int, Row]]


def _capture() -> Snapshot:
    """
    Every row of both tables, read straight out of the database

    Read through the tables rather than through the models: what is wanted is
    the row as it is stored, and going through the models would run the
    validators that keep the fields in step with each other — which is exactly
    what a restore has to avoid, since the rows it puts back are already in
    step with one another.

    The root project is left out. It is the peg the whole tree hangs off
    rather than a row anybody edits — never drawn, never reachable by a key,
    and written to the database at whatever moment the first project happens
    to need it. Counted here, that moment would end up inside somebody's
    change, and undoing that change would take the tree down with it.

    Notes are left out -- see `NOTE` above for why, and for what is done
    instead so that none is ever lost.
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


# The notes of todos on their way out of the database, kept from the moment
# the row is deleted until the change that deleted it has been written down.
#
# A note that is not in the snapshot cannot be read back off a row that is
# gone, and undoing a deletion has to bring the note back with the task. This
# is the one place a note is copied, and it holds only what a single key threw
# away.
_notes_of_deleted: Dict[int, str] = {}


@event.listens_for(Todo, "before_delete")
def _remember_note(_mapper, _connection, target: Todo) -> None:
    """
    Takes down a todo's note while there is still a row to read it from

    Hung off the model rather than written into the keys that delete, so that
    every way a todo can go -- deleted on its own, emptied out of the Bin, or
    carried off by the project it was filed in -- is covered by the one hook.
    """

    note = getattr(target, NOTE, "")

    if note:
        _notes_of_deleted[target.id] = note


@dataclass
class Change:
    """
    The rows one key left different, written down both ways round

    `before` is what they held before the key and `after` what they held after
    it, each carrying None for a row the other side has and this one never did.
    """

    before: Fragment
    after: Fragment


@dataclass
class Restored:
    """
    What one step through the history did to the rows, for the panes to answer

    The three are told apart because the panes do different things with them:
    what is gone has to be let go of, what came back or changed is worth
    pointing at, and the count of each is what the bar says.
    """

    # uuids of the rows that are no longer in the database
    gone: List[str] = field(default_factory=list)
    # uuids of the rows that were put back after not being there
    back: List[str] = field(default_factory=list)
    # uuids of the rows that were there either way and now hold something else
    changed: List[str] = field(default_factory=list)

    @property
    def touched(self) -> List[str]:
        """The rows that are still there and were written by the step"""

        return self.back + self.changed

    def summary(self) -> str:
        """
        What the step did, counted, for the bar to say after it

        A step can land anywhere in the tree — in a project nobody has open, in
        a pane that is not in front — so the count is often the only thing on
        screen that says the key did anything at all.
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
    The rows that differ between two snapshots, written down both ways round

    None when there are none: a save that wrote a field back the way it found
    it is a commit that changed nothing, and a change nobody can see is not one
    to press undo for.
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

        # A row that is gone takes its note with it, and there is nothing left
        # to read it back off. Whatever the deletion took down is written into
        # the side of the change that puts the row back, and only there: the
        # rows that are still in the database carry their own notes already
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
    Writes one side of a change back over the rows the other side left

    Every row the change names is deleted and the ones this side has are
    inserted again, rather than adding, editing and dropping being told apart
    and each handled its own way: a row is a row, and putting the stored one
    back is the same act whether or not something was standing there before it.

    `leaving` is the other side, and is read for nothing but which of the rows
    were there before this ran — which is what the panes are told, and what the
    bar counts.
    """

    session = manager.session
    restored = Restored()

    # What the todos being rewritten are carrying in their notes right now.
    # A row here is put back by being deleted and inserted again, and the row
    # going back in was read from a snapshot that never held a note -- so
    # without this, taking back an edit to a description would quietly empty
    # the note on the same task. Read before anything is deleted, which is the
    # last moment there is a row to read it from
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

    # Out in child-first order, so nothing is left pointing at a row that has
    # already gone
    for model in reversed(TABLES):
        rows = fragment.get(model.__tablename__)

        if not rows:
            continue

        table = model.__table__
        session.execute(delete(table).where(table.c.id.in_(list(rows))))

    # and back in parent-first
    for model in TABLES:
        rows = fragment.get(model.__tablename__)

        if not rows:
            continue

        values = [row for row in rows.values() if row is not None]

        # The note the row goes back with: the one it was carrying a moment
        # ago, or -- for a row that was not there to carry one -- the one the
        # deletion took down with it
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

    # Every model object the app is still holding was read before any of this
    # ran, so not one of them can be trusted. Expired rather than thrown out: a
    # row that is still there reads itself back the next time it is asked
    # anything, and one that is not is a row the panes are about to let go of.
    session.expire_all()

    return restored


class History:
    """
    The changes the panes have made, and the way back and forth through them

    Held by the app rather than by either pane: a key pressed over the tasks
    can move projects and the other way round, so there is one history over
    both of them, and one place the last change is taken back from whichever
    pane the cursor happens to be in.
    """

    def __init__(self) -> None:
        self._undo: List[Change] = []
        self._redo: List[Change] = []
        self._baseline: Optional[Snapshot] = None
        self._revision = -1

    @property
    def started(self) -> bool:
        return self._baseline is not None

    @property
    def can_undo(self) -> bool:
        return bool(self._undo)

    @property
    def can_redo(self) -> bool:
        return bool(self._redo)

    def start(self) -> None:
        """Take the database as it stands as the state nothing is before"""

        self._undo.clear()
        self._redo.clear()
        self._sync()

    def resync(self) -> None:
        """
        Take whatever the database holds now as what the next key changes

        Something outside the app wrote to it — another copy of todooit, or the
        file itself — and rows that arrived that way are not a change made here
        to be taken back. They become the state the next key is measured
        against instead of being folded into whatever it does.
        """

        if self.started:
            self._sync()

    def _sync(self) -> None:
        self._baseline = _capture()
        self._revision = manager.revision

        # Whatever was thrown away before this moment belongs to no change
        # that is still to be written down
        _notes_of_deleted.clear()

    def record(self) -> bool:
        """
        Writes down whatever the key just pressed changed, if it changed
        anything

        Nothing is read at all unless something has been written since the last
        look, so the keys that only walk around the panes — which is most of
        them, and all of the ones held down — cost a comparison of two numbers.
        """

        if not self.started or manager.revision == self._revision:
            return False

        assert self._baseline is not None

        after = _capture()
        change = _diff(self._baseline, after)

        # The change has taken what it needed out of them, and the next key
        # starts with nothing thrown away
        _notes_of_deleted.clear()

        self._baseline = after
        self._revision = manager.revision

        if change is None:
            return False

        self._undo.append(change)
        del self._undo[:-MAX_DEPTH]

        # The way forward was one of the futures of the state that has just
        # been left behind, and is not reachable from this one
        self._redo.clear()

        return True

    def undo(self) -> Optional[Restored]:
        """
        Puts the rows of the last change back the way they were before it

        None when there is nothing left to take back.
        """

        return self._step(self._undo, self._redo, forward=False)

    def redo(self) -> Optional[Restored]:
        """
        Puts back the change that was last taken back

        None when nothing has been taken back, or when a key has been pressed
        since: a change made from where the undo left off starts a history of
        its own, and the one that was walked out of is no longer ahead.
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

        # The step is not itself a change to be recorded: where it has just
        # arrived is the state the next key is measured against
        self._sync()

        return restored
