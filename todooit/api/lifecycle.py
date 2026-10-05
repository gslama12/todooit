"""
The todo lifecycle: the one place todos are completed, reopened and dated

The rules for completing, reopening, recurrence and the scheduled/due bounds
(bar "no due date on a recurring todo", a rule on the todo itself), applied as
explicit calls in memory and committed once. Nothing here runs as a side
effect of an unrelated save.

Every operation returns an `Outcome`: what it meant, in words the status bar
can show ("advanced to Mon 12 Oct, 2 steps moved with it").
"""

from collections import Counter
from dataclasses import dataclass, field
from datetime import datetime, timedelta
from enum import Enum
from typing import TYPE_CHECKING, Callable, Dict, List, Optional, Union

from .manager import manager
from .placement import root_of
from .recycle import revive_home
from .todo import Todo

if TYPE_CHECKING:  # pragma: no cover
    from .project import Project

class Change(Enum):
    """What an override did to a todo"""

    MOVED = "moved"
    ENDED = "recurrence ended"
    PULLED = "moved back"
    LOWERED = "due date moved"
    UNSCHEDULED = "unscheduled"
    UNDUE = "due date removed"


RECURRING_HAS_NO_DUE = (
    "A recurring todo has no due date; set its scheduled date instead"
)


def day_label(when: datetime) -> str:
    """A date the way the status bar names it, e.g. "Tue 7 Oct" """

    return f"{when:%a} {when.day} {when:%b}"


def _count(number: int, noun: str) -> str:
    return f"{number} {noun}" + ("" if number == 1 else "s")


class Refusal(Exception):
    """
    A step acting against a bound; the message is the warning to show

    Raised before anything is written, so a refused change changes nothing.
    """


@dataclass
class Override:
    """A todo other than the one acted on that a rule changed, and how"""

    todo: Todo
    what: Change


@dataclass
class Outcome:
    """
    What a lifecycle operation meant

    Falsy when there is nothing worth telling: a plain completion or reopen.
    """

    todo: Todo
    # The new scheduled date, when completing advanced a recurring todo
    advanced_to: Optional[datetime] = None
    overrides: List[Override] = field(default_factory=list)
    # Projects rebuilt to give a reopened orphan somewhere to live
    revived: List["Project"] = field(default_factory=list)

    @property
    def advanced(self) -> bool:
        return self.advanced_to is not None

    def __bool__(self) -> bool:
        return self.advanced or bool(self.overrides)

    def summary(self) -> str:
        """One line for the status bar; empty when there is nothing to tell"""

        todo = self.todo
        parts: List[Optional[str]] = []

        if self.advanced_to is not None:
            parts.append(f"advanced to {day_label(self.advanced_to)}")

        # The todo itself is only ever overridden by being placed (becoming a step)
        mine = {o.what for o in self.overrides if o.todo is todo}
        others = Counter(o.what for o in self.overrides if o.todo is not todo)

        parts += [say(todo) for what, say in _OWN.items() if what in mine]
        parts += [say(others[what], todo) for what, say in _OTHERS.items() if others[what]]

        return ", ".join(part for part in parts if part)


def _pulled(count: int, todo: Todo) -> Optional[str]:
    who = "its parent" if count == 1 else _count(count, "ancestor")
    return f"{who} moved back to {day_label(todo.scheduled)}" if todo.scheduled else None


# How each change reads in the summary, in the order it is told: for the todo
# acted on, then counted over the other todos it reached. None drops the part.
_OWN: Dict[Change, Callable[[Todo], Optional[str]]] = {
    Change.MOVED: lambda t: f"moved to {day_label(t.scheduled)}" if t.scheduled else None,
    Change.ENDED: lambda t: "stopped recurring",
    Change.LOWERED: lambda t: f"now due {day_label(t.due)}" if t.due else None,
}

_OTHERS: Dict[Change, Callable[[int, Todo], Optional[str]]] = {
    Change.MOVED: lambda n, t: f"{_count(n, 'step')} moved with it",
    Change.ENDED: lambda n, t: f"recurrence ended on {_count(n, 'step')}",
    Change.PULLED: _pulled,
    Change.LOWERED: lambda n, t: (
        f"{_count(n, 'step')} now due {day_label(t.due)}" if t.due else None
    ),
    Change.UNSCHEDULED: lambda n, t: f"{_count(n, 'step')} unscheduled",
    Change.UNDUE: lambda n, t: f"{_count(n, 'step')} no longer due",
}


def complete(todo: Todo) -> Outcome:
    """
    Complete a todo and its family, or advance it if it recurs, steps included
    """

    stamp = datetime.now()
    outcome = Outcome(todo)

    if todo.recurrence is not None:
        _advance(todo, stamp, outcome)
    else:
        _complete_family(todo, stamp, outcome)

    manager.save(todo)
    return outcome


def reopen(todo: Todo) -> Outcome:
    """
    Reopen a todo's whole family and all its ancestors

    Nothing a completion removed comes back: undo is for that. A task whose
    project was dropped while it sat completed is filed back under its origin
    path, so an open todo always has a project to live in. Completed steps
    ignore their parent's dates, so a reopened one is fitted to them again.
    """

    outcome = Outcome(todo)
    _reopen_all([*todo.ancestors, *todo.family])

    top = (todo.ancestors or [todo])[-1]
    _raise_to_floor(top, outcome)
    _lower_to_ceiling(top, outcome)

    manager.save(todo)
    outcome.revived = revive_home(root_of(todo))
    return outcome


def schedule(todo: Todo, when: Optional[datetime]) -> Outcome:
    """
    Plan a todo for a day, or take its day away; steps on its old day follow
    it, and its date is a floor for the rest
    """

    outcome = Outcome(todo)
    parent = todo.parent_todo

    # An empty step date means "follow the parent"
    if when is None and parent is not None:
        when = parent.scheduled

    _carry(todo, "scheduled", when, outcome)
    _pull_back_ancestors(todo, outcome)
    _raise_to_floor(todo, outcome)

    manager.save(todo)
    return outcome


def set_due(todo: Todo, when: Optional[datetime]) -> Outcome:
    """
    Give a todo a deadline, or take it away; steps due with it follow it,
    and its date is a ceiling for the rest
    """

    outcome = Outcome(todo)
    parent = todo.parent_todo

    if when is not None:
        if todo.recurrence is not None:
            raise Refusal(RECURRING_HAS_NO_DUE)

        _refuse_past_ceiling(todo, when)

    # An empty step deadline means "the parent's deadline"
    elif parent is not None:
        when = parent.due

    _carry(todo, "due", when, outcome)
    _lower_to_ceiling(todo, outcome)

    manager.save(todo)
    return outcome


def set_recurrence(todo: Todo, every: Optional[timedelta]) -> Outcome:
    """
    Make a todo come back every interval, or stop it recurring

    Refused under a recurring ancestor or one with a due date.
    """

    outcome = Outcome(todo)

    if every is None:
        todo.recurrence = None
        manager.save(todo)
        return outcome

    _refuse_under_owner(todo)
    undated = todo.scheduled is None

    # The todo's own rule (no due date on a recurring todo) turns a deadline
    # into the first day here
    todo.recurrence = every
    _end_recurrence_below(todo, outcome)

    # A cadence needs a first day: that deadline, else today
    if undated:
        todo.scheduled = todo.scheduled or datetime.now()
        _pull_back_ancestors(todo, outcome)
        _raise_to_floor(todo, outcome)

    manager.save(todo)
    return outcome


def place(todo: Todo, parent: Union[Todo, "Project"]) -> Outcome:
    """
    Put a todo under a todo or a project, fitted to its new ancestors

    Becoming a step is never refused: the todo takes what its new parent
    allows instead. Leaving a todo for a project keeps its values.
    Where it goes among its siblings is the caller's business.
    """

    outcome = Outcome(todo)

    # A new todo is written whole at the commit, not half-fitted by a read
    with manager.session.no_autoflush:
        if isinstance(parent, Todo):
            todo.parent_project = None
            todo.parent_todo = parent
            _fit(todo, parent, outcome)
        else:
            todo.parent_todo = None
            todo.parent_project = parent

    manager.save(todo)
    return outcome


def _fit(todo: Todo, parent: Todo, outcome: Outcome) -> None:
    """
    Becoming a step is fitted: an empty date is the parent's; an earlier day
    rises to the parent's floor and a later deadline comes down to its
    ceiling, taking the todo's own steps along. Under an ancestor that recurs
    or has a deadline, nothing in the family recurs any more.
    """

    if any(a.recurrence is not None or a.due is not None for a in todo.ancestors):
        for node in todo.family:
            if node.recurrence is not None:
                node.recurrence = None
                outcome.overrides.append(Override(node, Change.ENDED))

    floor = parent.scheduled

    if todo.scheduled is None:
        todo.scheduled = floor
    elif floor is not None and todo.scheduled.date() < floor.date():
        todo.scheduled = floor
        outcome.overrides.append(Override(todo, Change.MOVED))

    _raise_to_floor(todo, outcome)

    # The ceiling: an empty deadline is the parent's, a later one comes down
    ceiling = parent.due

    if todo.due is None:
        todo.due = ceiling
    elif ceiling is not None and todo.due.date() > ceiling.date():
        todo.due = ceiling
        outcome.overrides.append(Override(todo, Change.LOWERED))

    _lower_to_ceiling(todo, outcome)


def _refuse_under_owner(todo: Todo) -> None:
    """
    One cadence per line: a todo with a recurring ancestor never recurs itself,
    nor, under a deadline, does one with an ancestor that has a due date
    """

    for ancestor in todo.ancestors:
        name = f'Can\'t recur: its ancestor "{ancestor.description}"'

        if ancestor.recurrence is not None:
            raise Refusal(f"{name} already recurs")

        if ancestor.due is not None:
            raise Refusal(f"{name} is due {day_label(ancestor.due)}")


def _end_recurrence_below(todo: Todo, outcome: Outcome) -> None:
    """One cadence per line: a recurring todo owns the cadence of its whole family"""

    for step in todo.descendants:
        if step.recurrence is not None:
            step.recurrence = None
            outcome.overrides.append(Override(step, Change.ENDED))


def _refuse_past_ceiling(todo: Todo, when: datetime) -> None:
    """A step is never due after its parent"""

    parent = todo.parent_todo

    if parent is None or parent.due is None:
        return

    if when.date() > parent.due.date():
        raise Refusal(
            f"Can't be due after its parent's due date, {day_label(parent.due)}"
        )


def _lower_to_ceiling(todo: Todo, outcome: Outcome) -> None:
    """
    The ceiling: every step due after its parent, or not at all, moves onto
    its date; earlier ones stay (and are the ceiling for their own steps). A
    recurring step stops recurring, since a todo under a deadline never recurs.
    A completed step keeps its dates, and so does everything under it.
    """

    ceiling = todo.due

    if ceiling is None:
        return

    for step in todo.todos:
        if step.is_completed:
            continue

        if step.recurrence is not None:
            step.recurrence = None
            outcome.overrides.append(Override(step, Change.ENDED))

        if step.due is None or step.due.date() > ceiling.date():
            step.due = ceiling
            outcome.overrides.append(Override(step, Change.LOWERED))

        _lower_to_ceiling(step, outcome)


def _carry(todo: Todo, attr: str, when: Optional[datetime], outcome: Outcome) -> None:
    """
    Give a todo a new date, and every step still on its old one the same:
    a step with a date of its own stays, and so does everything under it.
    A completed step stays too, until it is reopened.
    """

    old = getattr(todo, attr)
    setattr(todo, attr, when)

    if old is None or old == when:
        return

    what = _CARRIED[attr, when is not None]

    for step in todo.todos:
        if step.is_pending and getattr(step, attr) == old:
            _carry(step, attr, when, outcome)
            outcome.overrides.append(Override(step, what))


# What following a parent did to a step, by date and by whether it still has one
_CARRIED = {
    ("scheduled", True): Change.MOVED,
    ("scheduled", False): Change.UNSCHEDULED,
    ("due", True): Change.LOWERED,
    ("due", False): Change.UNDUE,
}


def _pull_back_ancestors(todo: Todo, outcome: Outcome) -> None:
    """An early step pulls back every ancestor scheduled later than it to its day"""

    when = todo.scheduled

    if when is None:
        return

    for ancestor in todo.ancestors:
        if ancestor.scheduled is not None and ancestor.scheduled.date() > when.date():
            ancestor.scheduled = when
            outcome.overrides.append(Override(ancestor, Change.PULLED))


def _raise_to_floor(todo: Todo, outcome: Outcome) -> None:
    """
    The floor: every step scheduled before its parent's date, or not at all,
    moves onto it; later ones stay (and are the floor for their own steps).
    A completed step keeps its dates, and so does everything under it.
    """

    floor = todo.scheduled

    if floor is None:
        return

    for step in todo.todos:
        if step.is_completed:
            continue

        if step.scheduled is None or step.scheduled.date() < floor.date():
            step.scheduled = floor
            outcome.overrides.append(Override(step, Change.MOVED))

        _raise_to_floor(step, outcome)


def _complete_family(todo: Todo, stamp: datetime, outcome: Outcome) -> None:
    """The whole family is completed at one moment and stops recurring"""

    for node in todo.family:
        if node.recurrence is not None:
            outcome.overrides.append(Override(node, Change.ENDED))

        node.recurrence = None
        node.pending = False
        # After `pending`, whose validator stamps each row with its own moment
        node.completed_at = stamp


def _advance(todo: Todo, stamp: datetime, outcome: Outcome) -> None:
    """
    The todo stays open one interval on, its family reopens, and steps
    planned before the new date move onto it
    """

    assert todo.recurrence is not None

    new_date = (todo.scheduled or stamp) + todo.recurrence
    todo.scheduled = new_date
    outcome.advanced_to = new_date

    _reopen_all(todo.family)

    # Never the ancestors: an advance only ever moves later
    _raise_to_floor(todo, outcome)


def _reopen_all(todos: List[Todo]) -> None:
    for node in todos:
        node.pending = True
