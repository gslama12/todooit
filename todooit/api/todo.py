from collections import defaultdict
from typing import TYPE_CHECKING, Callable, Dict, Literal, Optional, Union
from datetime import date, datetime
from typing import List
from sqlalchemy import ForeignKey, Index, select, text
from sqlalchemy.orm import Mapped, mapped_column, relationship, validates
from .cadence import Cadence, CadenceType
from .model import TodooitModel
from .manager import manager


if TYPE_CHECKING:  # pragma: no cover
    from todooit.api.lifecycle import Outcome
    from todooit.api.project import Project


# Priority: 1 = most urgent, 3 = least, 0 = none
MAX_PRIORITY = 3

# Every sort falls back to the manual order for ties
TodoSortModeType = Literal["priority", "due", "scheduled"]


# Most urgent first; unprioritized (0) last
def priority_key(todo: "Todo") -> tuple:
    return (todo.priority == 0, todo.priority, todo.order_index)


# Undated todos sort last
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
    Write the order of a sort mode into order_index, for every sibling run

    Used when leaving a sort, so rows stay where they were drawn.
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
    The todos sorted by `mode`, or unchanged if the mode is unknown/None
    """

    key = SORT_KEYS.get(mode or "")

    if key is None:
        return list(todos)

    return sorted(todos, key=key)


class Todo(TodooitModel):
    # Day panes query pending work by schedule; the Bin queries binned rows
    # (partial index, since almost no rows are binned)
    __table_args__ = (
        Index("ix_todo_pending_scheduled", "pending", "scheduled"),
        Index(
            "ix_todo_binned_at",
            "binned_at",
            sqlite_where=text("binned_at IS NOT NULL"),
        ),
    )

    description: Mapped[str] = mapped_column(default="")
    due: Mapped[Optional[datetime]] = mapped_column(default=None)
    # Planned work day (as opposed to the `due` deadline)
    scheduled: Mapped[Optional[datetime]] = mapped_column(default=None)
    # Marker: the todo has been handed off to an AI agent
    agent: Mapped[bool] = mapped_column(default=False)
    recurrence: Mapped[Optional[Cadence]] = mapped_column(CadenceType, default=None)
    priority: Mapped[int] = mapped_column(default=0)
    pending: Mapped[bool] = mapped_column(default=True)
    completed_at: Mapped[Optional[datetime]] = mapped_column(default=None)
    binned_at: Mapped[Optional[datetime]] = mapped_column(default=None)
    # Project path recorded when the todo's project was deleted; used to revive it
    origin_path: Mapped[str] = mapped_column(default="")
    # Deferred: panes load many todos at once and never need the note text
    note: Mapped[str] = mapped_column(default="", deferred=True)
    # Attached file paths, one per line (files are never copied)
    attachments: Mapped[str] = mapped_column(default="", deferred=True)

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
        remote_side="Todo.id",
    )

    # No delete-orphan: a step briefly has no parent while being moved
    todos: Mapped[List["Todo"]] = relationship(
        "Todo",
        back_populates="parent_todo",
        cascade="all",
        order_by="Todo.order_index",
    )

    # No due date on a recurring todo, a data-shape rule of the todo itself:
    # a recurring todo is planned by its scheduled date and has no due date.
    # Held the moment either field is set, so no path can write the two together.

    @validates("recurrence")
    def pend_recurring(self, key, value):
        if value is not None:
            self.pending = True

            if self.due is not None:
                self.scheduled = self.scheduled or self.due
                self.due = None

        return value

    @validates("due")
    def no_due_while_recurring(self, key, value):
        if value is not None and self.recurrence is not None:
            self.scheduled = self.scheduled or value
            return None

        return value

    @validates("pending")
    def stamp_completion(self, key, value):
        # On the field itself so every path that completes a todo is stamped
        self.completed_at = None if value else datetime.now()

        return value

    @classmethod
    def from_id(cls, _id: str) -> "Todo":
        _id = _id.removeprefix("Todo_")
        query = select(Todo).where(Todo.id == _id)
        res = manager.session.execute(query).scalars().first()
        assert res is not None
        return res

    @property
    def parent(self) -> Optional[Union["Project", "Todo"]]:
        """
        The parent project or todo; None for an orphan (see `is_orphan`)
        """

        if self.parent_project:
            return self.parent_project

        return self.parent_todo

    @property
    def is_orphan(self) -> bool:
        """
        Whether this todo's project was deleted (only happens to binned or completed todos)
        """

        return self.parent_project is None and self.parent_todo is None

    @property
    def is_binned(self) -> bool:
        return self.binned_at is not None

    @property
    def ancestors(self) -> List["Todo"]:
        """
        Every todo this one is nested under, nearest first
        """

        found: List["Todo"] = []
        node = self.parent_todo

        while node is not None:
            found.append(node)
            node = node.parent_todo

        return found

    @property
    def descendants(self) -> List["Todo"]:
        """
        Every todo nested under this one, at every depth
        """

        found: List["Todo"] = []

        for child in self.todos:
            found.append(child)
            found.extend(child.descendants)

        return found

    @property
    def family(self) -> List["Todo"]:
        """
        This todo plus all its descendants
        """

        return [self, *self.descendants]

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
        Pending, unbinned todos under this one, at every depth
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
        from . import lifecycle

        todo = Todo()
        lifecycle.place(todo, self)
        return todo

    def add_sibling(self) -> "Todo":
        from . import lifecycle

        parent = self.parent
        assert parent is not None

        todo = Todo(order_index=self.order_index + 1)
        lifecycle.place(todo, parent)
        return todo

    # ------------------- Moving between levels --------------------

    def _renumber(self, todos: List["Todo"]) -> None:
        """
        Renumber a whole run in the given order (fixes gaps and duplicate indexes)
        """

        for order, todo in enumerate(todos):
            todo.order_index = order
            self.session.add(todo)

    @property
    def previous_sibling(self) -> Optional["Todo"]:
        if self.is_first_sibling():
            return None

        siblings = self.siblings
        return siblings[siblings.index(self) - 1]

    def indent(self, parent: Optional["Todo"] = None) -> Optional["Outcome"]:
        """
        Make this todo the last step of `parent` (default: the previous sibling)

        Returns how it was fitted to its new ancestors, or None if there
        is nothing to indent under.
        """

        from . import lifecycle

        parent = parent or self.previous_sibling

        if parent is None:
            return None

        self._renumber(list(parent.todos) + [self])
        return lifecycle.place(self, parent)

    def unindent(self) -> Optional["Outcome"]:
        """
        Move this todo out of its parent todo, placing it right after the parent

        Returns how it was placed, or None if already top level.
        """

        from . import lifecycle

        parent = self.parent_todo

        if parent is None:
            return None

        grandparent = parent.parent

        # The parent is an orphan: nowhere to move to
        if grandparent is None:  # pragma: no cover
            return None

        run = [todo for todo in parent.siblings if todo.id != self.id]
        after = run.index(parent) + 1
        self._renumber(run[:after] + [self] + run[after:])

        return lifecycle.place(self, grandparent)

    def move_to(self, project: "Project") -> "Outcome":
        """
        Move this todo (with its children) to the end of `project`

        A child todo becomes top level, keeping its values; bin state is
        left untouched.
        """

        from . import lifecycle

        # Excludes self, in case it's already somewhere inside `project`
        run = [todo for todo in project.todos if todo.id != self.id]
        self._renumber(run + [self])

        return lifecycle.place(self, project)

    # ------------------- Helpers --------------------

    def set_priority(self, priority: int) -> None:
        self.priority = priority
        self.save()

    def toggle_agent(self) -> None:
        self.agent = not self.agent
        self.save()

    def toggle_complete(self) -> "Outcome":
        """
        Complete or reopen, whichever this todo's state calls for
        """

        from . import lifecycle

        if self.pending:
            return lifecycle.complete(self)

        return lifecycle.reopen(self)

    @property
    def is_completed(self) -> bool:
        return not self.pending

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
        Whether this pending todo was scheduled for a day before today

        Compared by date only: something scheduled this morning is not late tonight.
        """

        if not self.scheduled:
            return False

        return self.pending and self.scheduled.date() < date.today()

    @classmethod
    def all(cls) -> List["Todo"]:
        query = select(Todo)
        return list(manager.session.execute(query).scalars().all())
