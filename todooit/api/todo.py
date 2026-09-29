from collections import defaultdict
from typing import TYPE_CHECKING, Callable, Dict, Literal, Optional, Union
from datetime import date, datetime, timedelta
from typing import List
from sqlalchemy import ForeignKey, Index, select, text
from sqlalchemy.orm import Mapped, mapped_column, relationship, validates
from .model import TodooitModel
from .manager import manager


if TYPE_CHECKING:  # pragma: no cover
    from todooit.api.project import Project


# Priority runs from 1, the most urgent, down to 3, the least, and 0 means
# none was set. Written down here so that anything reading a priority off
# typed text has one place to ask how far the scale goes
MAX_PRIORITY = 3

# The orders a pane of todos can be read in. Every one of them ends on the
# order the todos were filed in by hand, so the rows a sort has nothing to say
# about — the ones nobody prioritized, or put a date on — keep the order they
# were given rather than being shuffled around by it.
TodoSortModeType = Literal["priority", "due", "scheduled"]


# The most urgent first, and everything unprioritized after the lot of them:
# priority 1 is the top of the scale and 0 means it was never set, so the rows
# without one are pushed past the end rather than sorting ahead of p1
def priority_key(todo: "Todo") -> tuple:
    return (todo.priority == 0, todo.priority, todo.order_index)


# What a date sort does with the rows carrying no date: they go last. A todo
# nobody put a day on is not due at the beginning of time, it is simply not
# something the sort can place.
def _date_key(attr: str) -> Callable[["Todo"], tuple]:
    def key(todo: "Todo") -> tuple:
        value = getattr(todo, attr)
        return (value is None, value or datetime.max, todo.order_index)

    return key


SORT_KEYS: Dict[str, Callable[["Todo"], tuple]] = {
    "priority": priority_key,
    "due": _date_key("due"),
    "scheduled": _date_key("scheduled"),
}


def freeze_sort_order(mode: Optional[str]) -> None:
    """
    Writes the order a sort reads the todos in back into the filing

    What hands a pane back to the hand that filed it. The rows keep the places
    they were just drawn in, and from here on they are in those places because
    that is where they are filed rather than because an order is being worked
    out over them on every redraw — which is what makes a row moved by hand
    stay where it was put.

    Every run of siblings in the database is written, not just the one being
    moved in: the order belongs to the pane rather than to the row, so dropping
    it for one run while the rest of the pane still read by priority would
    shuffle the blocks the cursor is nowhere near.
    """

    if SORT_KEYS.get(mode or "") is None:
        return

    groups: Dict[tuple, List["Todo"]] = defaultdict(list)

    for todo in manager.session.query(Todo).all():
        groups[(todo.parent_project_id, todo.parent_todo_id)].append(todo)

    for todos in groups.values():
        for index, todo in enumerate(sort_todos(todos, mode)):
            todo.order_index = index

    manager.commit()


def sort_todos(todos: List["Todo"], mode: Optional[str]) -> List["Todo"]:
    """
    A run of todos in the order the pane reads them in

    No mode — or one nothing is known about — hands the list straight back, in
    the order the todos were filed in.
    """

    key = SORT_KEYS.get(mode or "")

    if key is None:
        return list(todos)

    return sorted(todos, key=key)


class Todo(TodooitModel):
    # The two ways a pane asks for todos that a foreign key does not already
    # cover: the day panes read pending work by the day it is planned for, and
    # the Bin reads the rows that have one at all. The Bin index is partial
    # because that is exactly the question `binned_tasks` asks -- the rows
    # with no bin date are the overwhelming majority and are never looked up
    # through it. The names match `todooit/utils/database.py`, which is what
    # puts the same indexes on a database written before they existed.
    __table_args__ = (
        Index("ix_todo_pending_scheduled", "pending", "scheduled"),
        Index(
            "ix_todo_binned_at",
            "binned_at",
            sqlite_where=text("binned_at IS NOT NULL"),
        ),
    )

    id: Mapped[int] = mapped_column(primary_key=True, autoincrement=True)
    order_index: Mapped[int] = mapped_column(default=-1)
    description: Mapped[str] = mapped_column(default="")
    due: Mapped[Optional[datetime]] = mapped_column(default=None)
    # The day the todo is planned to be worked on, as opposed to the deadline
    # that `due` sets
    scheduled: Mapped[Optional[datetime]] = mapped_column(default=None)
    # Whether the todo has been handed to an AI that is off working on it.
    # Nothing but a marker: it says the job is out of your hands for the
    # moment, and says nothing about how far along it is or when it comes back
    agent: Mapped[bool] = mapped_column(default=False)
    recurrence: Mapped[Optional[timedelta]] = mapped_column(default=None)
    priority: Mapped[int] = mapped_column(default=0)
    pending: Mapped[bool] = mapped_column(default=True)
    # When the todo was ticked off. Never shown on a row of its own pane: it is
    # what the Completed project orders its rows by, so that the last thing
    # finished is the first thing seen there
    completed_at: Mapped[Optional[datetime]] = mapped_column(default=None)
    # When the todo was moved to the Bin. A binned todo is shown in the Bin
    # project and nowhere else: not in the project it was filed under, and not
    # in any of the fixed projects that gather work up from across the tree
    binned_at: Mapped[Optional[datetime]] = mapped_column(default=None)
    # The path of the project the todo was filed under, written down at the
    # moment that project stopped existing. It is what a todo outliving its
    # project is put back into when it is revived, and what says where it came
    # from while there is nothing left to point at
    origin_path: Mapped[str] = mapped_column(default="")
    # Free text hanging off the todo, edited in a window of its own rather than
    # in the row: the phone number to call, the steps, the reason it is blocked
    #
    # Left behind when a todo is read, and fetched only when something asks for
    # it. It is the one field with no length to speak of, and nearly everything
    # that reads todos reads a great many of them to draw a pane -- a query for
    # a day's work would otherwise carry every note in the database across with
    # it. The window that edits it asks for one note at a time, which is the
    # only place the text is actually wanted.
    note: Mapped[str] = mapped_column(default="", deferred=True)
    # The files this todo points at, one path per line, and nothing but the
    # paths: the file itself is never copied anywhere, so attaching costs
    # nothing and moving the file breaks only the way back to it.
    #
    # Kept beside the note rather than inside it because an attachment is not
    # something the note *says* - it is something the task has - and a line of
    # text can be typed over, indented, quoted and deleted by accident.
    # Deferred for the same reason the note is: nothing that draws a pane
    # wants it.
    attachments: Mapped[str] = mapped_column(default="", deferred=True)

    # --------------------------------------------------------------
    # ------------------- Relationships ----------------------------
    # --------------------------------------------------------------

    parent_project_id: Mapped[Optional[int]] = mapped_column(
        ForeignKey("project.id"), index=True
    )
    parent_project: Mapped[Optional["Project"]] = relationship(
        "Project",
        back_populates="todos",
    )

    parent_todo_id: Mapped[Optional[int]] = mapped_column(
        ForeignKey("todo.id"), index=True
    )
    parent_todo: Mapped[Optional["Todo"]] = relationship(
        "Todo",
        back_populates="todos",
        remote_side=[id],
    )

    # Deleting the task still takes its steps with it, but a step lifted out
    # of it is not thereby deleted: `delete-orphan` here made the `U` key —
    # which takes a step out of the task it is a step of — sometimes delete
    # the step instead of moving it, since a step on its way to a project is
    # briefly attached to neither
    todos: Mapped[List["Todo"]] = relationship(
        "Todo",
        back_populates="parent_todo",
        cascade="all",
        order_by=order_index,
    )

    @validates("recurrence")
    def validate_pending(self, key, value):
        if value is not None:
            self.pending = True

        return value

    @validates("pending")
    def stamp_completion(self, key, value):
        """
        Dates the todo the moment it is ticked off, and undates it when it is
        unticked

        Hung off the field itself rather than off `toggle_complete`, so that
        every way a todo can be finished is stamped: the hooks that carry a
        parent or a child along with it, and the one that bounces a recurring
        todo straight back to pending, all go through here.
        """

        self.completed_at = None if value else datetime.now()

        return value

    @classmethod
    def from_id(cls, _id: str) -> "Todo":
        _id = _id.lstrip("Todo_")
        query = select(Todo).where(Todo.id == _id)
        res = manager.session.execute(query).scalars().first()
        assert res is not None
        return res

    @property
    def parent(self) -> Optional[Union["Project", "Todo"]]:
        """
        Whatever the todo hangs off, or nothing at all

        A todo normally has one or the other. It can have neither: one that
        outlived the project it was filed under keeps nothing but the path it
        came from, and hangs off nothing until it is put back into a project.
        """

        if self.parent_project:
            return self.parent_project

        return self.parent_todo

    @property
    def is_orphan(self) -> bool:
        """
        Whether the project this todo was filed under is gone

        Only a todo nobody is expected to work on right now can be left this
        way: one in the Bin, or one already done and kept in the log.
        """

        return self.parent_project is None and self.parent_todo is None

    @property
    def is_binned(self) -> bool:
        return self.binned_at is not None

    @property
    def descendants(self) -> List["Todo"]:
        """
        Every todo filed under this one, at any depth
        """

        found: List["Todo"] = []

        for child in self.todos:
            found.append(child)
            found.extend(child.descendants)

        return found

    @property
    def has_same_parent_kind(self) -> bool:
        return self.parent_todo is not None

    @property
    def status(self) -> str:
        if self.is_completed:
            return "completed"

        if self.is_overdue:
            return "overdue"

        return "pending"

    @property
    def total_children(self) -> int:
        """
        Every todo still to be done under this one, counted at every level

        The steps already done are left out: they are still drawn under this
        todo, but what the count is for is how much of the task is left, which
        is what a collapsed row has no other way of saying. A step thrown in
        the Bin is not work left either — it is not drawn here at all.
        """

        return sum(
            1 + todo.total_children
            for todo in self.todos
            if todo.pending and not todo.is_binned
        )

    @property
    def siblings(self) -> List["Todo"]:
        if self.parent_project:
            return self.parent_project.todos

        if self.parent_todo:
            return self.parent_todo.todos

        return []

    def add_todo(self) -> "Todo":
        todo = Todo(parent_todo=self)
        todo.save()
        return todo

    def _add_sibling(self) -> "Todo":
        todo = Todo(
            parent_todo=self.parent_todo,
            parent_project=self.parent_project,
            order_index=self.order_index + 1,
        )
        todo.save()
        return todo

    # --------------------------------------------------------------
    # ------------------- Moving between levels --------------------
    # --------------------------------------------------------------

    def _renumber(self, todos: List["Todo"]) -> None:
        """
        Files a run of todos in the order they are handed over

        The whole run is written back rather than just the todo that moved: a
        run built up by hand can have holes in it, or two todos filed at the
        same index, and either would leave the moved todo landing somewhere
        other than where it was put.
        """

        for order, todo in enumerate(todos):
            todo.order_index = order
            self.session.add(todo)

    @property
    def previous_sibling(self) -> Optional["Todo"]:
        """
        The todo filed directly above this one, or None if it opens the run
        """

        if self.is_first_sibling():
            return None

        siblings = self.siblings
        return siblings[siblings.index(self) - 1]

    def indent(self, parent: Optional["Todo"] = None) -> Optional["Todo"]:
        """
        File this todo under the one above it, as a step of it

        It moves under the todo it was sitting beneath, so what it becomes a
        step of is the row above it. Everything already filed under it comes
        along — it is the todo that moves, not the family — and it lands at
        the end of that todo's steps, which is where a step added by hand
        would have gone.

        Which todo that is can be handed over, since a pane being read in an
        order of its own draws its rows in an order the filing does not know
        about; left out, it is the todo filed directly above this one.

        A todo with nothing above it to move under hands back None rather
        than moving anywhere.
        """

        parent = parent or self.previous_sibling

        if parent is None:
            return None

        steps = list(parent.todos)

        self.parent_project = None
        self.parent_todo = parent
        self._renumber(steps + [self])

        self.save()
        return parent

    def unindent(self) -> Optional[Union["Project", "Todo"]]:
        """
        Take this todo out of the task it is a step of

        It lands directly beside that task rather than at the end of the run
        it is joining: a step pulled out of a task belongs with the task it
        was part of, not at the bottom of the project. Its own steps come
        along with it.

        A todo filed straight under a project is already at the top of its
        run, and hands back None.
        """

        parent = self.parent_todo

        if parent is None:
            return None

        grandparent = parent.parent

        # The task this is a step of outlived the project it was filed under,
        # so there is nothing out here to land beside
        if grandparent is None:  # pragma: no cover
            return None

        run = [todo for todo in parent.siblings if todo.id != self.id]
        after = run.index(parent) + 1

        if isinstance(grandparent, Todo):
            self.parent_todo = grandparent
        else:
            self.parent_todo = None
            self.parent_project = grandparent

        self._renumber(run[:after] + [self] + run[after:])

        self.save()
        return grandparent

    def move_to(self, project: "Project") -> None:
        """
        File this todo under another project, at the bottom of what is there

        The whole task moves, its steps along with it, and it lands at the end
        of that project's run — where a task added to it by hand would have
        gone, and where a task arriving from elsewhere is looked for.

        A step of another task is lifted out of it on the way: what a project
        holds is tasks, so a step moved into one stops being a step. Nothing
        else about the todo changes — one in the Bin is still in the Bin
        afterwards, and comes back out into the project it has just been given.
        """

        # What the project holds already, this todo left out of it: a step
        # moved into the project it was already filed somewhere inside is
        # taken out of the run before being put back on the end of it
        run = [todo for todo in project.todos if todo.id != self.id]

        self.parent_todo = None
        self.parent_project = project
        self._renumber(run + [self])

        self.save()

    # ----------- HELPER FUNCTIONS --------------

    def set_priority(self, priority: int) -> None:
        self.priority = priority
        self.save()

    def toggle_agent(self) -> None:
        self.agent = not self.agent
        self.save()

    def toggle_complete(self) -> None:
        self.pending = not self.pending
        self.save()

    @property
    def is_completed(self) -> bool:
        return self.pending == False

    @property
    def is_pending(self) -> bool:
        return self.pending

    @property
    def is_overdue(self) -> bool:
        if not self.due:
            return False

        return self.pending and self.due < datetime.now()

    @property
    def is_overscheduled(self) -> bool:
        """
        Whether the day this was planned to be worked on has already gone by

        The other half of `is_overdue`: a deadline that has passed says the
        work is late, where a planning day that has passed says only that the
        plan did not survive the day it was made for. That is a day-at-a-time
        question, so the hour a todo was scheduled at has no say in it: work
        planned for this morning is still today's work this evening.

        What it is for are the panes work is planned in. They carry what has
        slipped onto today rather than leaving it behind in a week nobody
        opens again, and mark it as having slipped, since a day that was
        missed is a day to be picked again.
        """

        if not self.scheduled:
            return False

        return self.pending and self.scheduled.date() < date.today()

    @classmethod
    def all(cls) -> List["Todo"]:
        query = select(Todo)
        return list(manager.session.execute(query).scalars().all())
