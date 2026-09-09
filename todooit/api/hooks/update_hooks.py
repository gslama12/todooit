from datetime import datetime
from typing import Iterator, List, Optional
from sqlalchemy import event, inspect, update
from ..todo import Todo


def _descendants(todo: Todo) -> Iterator[Todo]:
    """
    Every todo filed under this one, at any depth
    """

    for child in todo.todos:
        yield child
        yield from _descendants(child)


def _ancestors(todo: Todo) -> Iterator[Todo]:
    """
    The todo this one hangs off, the one that hangs off, and so on up
    """

    node = todo.parent_todo

    while node is not None:
        yield node
        node = node.parent_todo


def _set_pending(connection, todos: List[Todo]) -> None:
    ids = [todo.id for todo in todos]

    if not ids:
        return

    query = (
        update(Todo)
        .where(Todo.id.in_(ids))
        .values(pending=True, completed_at=None)
    )
    connection.execute(query)


def _set_completed(connection, todos: List[Todo], stamp: datetime) -> None:
    ids = [todo.id for todo in todos]

    if not ids:
        return

    query = (
        update(Todo)
        .where(Todo.id.in_(ids))
        .values(pending=False, completed_at=stamp)
    )
    connection.execute(query)


def _bounce_recurrence(connection, todo: Todo, stamp: datetime) -> None:
    """
    Moves a repeating todo on an interval and hands it back, pending

    What ticking one off does, done to a todo that is being carried along by
    another rather than ticked itself, and written straight to the database
    for the same reason the rest of the cascade is.
    """

    assert todo.recurrence is not None

    when = (todo.scheduled or stamp) + todo.recurrence
    query = (
        update(Todo)
        .where(Todo.id == todo.id)
        .values(pending=True, completed_at=None, scheduled=when)
    )
    connection.execute(query)


def _complete(connection, todos: List[Todo], stamp: datetime) -> None:
    """
    Ticks off the ones that can be, and moves the repeating ones on instead

    Nothing that repeats is ever left finished, being carried along by the
    work around it included: what finishing it means is that it comes round
    again. It is bounced here, at the moment it was carried off, rather than
    left sitting completed for the next unrelated edit to notice.
    """

    _set_completed(
        connection, [todo for todo in todos if todo.recurrence is None], stamp
    )

    for todo in todos:
        if todo.recurrence is not None:
            _bounce_recurrence(connection, todo, stamp)


def _changed(todo: Todo, field: str) -> bool:
    return inspect(todo).attrs[field].history.has_changes()


@event.listens_for(Todo, "before_update")
def update_children_to_pending(_, connection, target: Todo):
    """
    Unticking a todo unticks everything underneath it

    The whole subtree at once rather than one level of it: what is done is the
    task, and a task is undone the moment any part of it is.
    """

    if not target.pending:
        return

    if any(todo.pending for todo in target.todos):
        return

    _set_pending(connection, list(_descendants(target)))


@event.listens_for(Todo, "before_update")
def update_children_to_completed(_, connection, target: Todo):
    """
    Ticking a todo ticks everything underneath it, at every depth
    """

    if target.pending:
        return

    stamp = target.completed_at or datetime.now()
    _complete(connection, list(_descendants(target)), stamp)


@event.listens_for(Todo, "before_update")
def update_parent_to_pending(mapper, connection, target: Todo):
    """
    Unticking a todo unticks every todo it is filed under

    All the way up rather than one level: a task with anything left to do in
    it is not finished, however deep in it that thing sits.
    """

    if not target.pending or not target.parent_todo:
        return

    _set_pending(connection, list(_ancestors(target)))


@event.listens_for(Todo, "before_update")
def update_parent_to_completed(mapper, connection, target: Todo):
    """
    Ticking off the last of a todo's children ticks the todo itself

    Carried on up for as long as it keeps being the last one: finishing the
    final step of the final part of something finishes the whole of it, and
    the whole of it is stamped with the moment that step was done.
    """

    if target.pending or not target.parent_todo:
        return

    stamp = target.completed_at or datetime.now()

    # The rows written here are only written straight to the database, so the
    # ones already dealt with still read as pending in the session: they are
    # kept track of rather than read back
    completed = {target.id}

    for node in _ancestors(target):
        if any(
            child.pending and child.id not in completed for child in node.todos
        ):
            break

        # A task that repeats comes round again rather than finishing, and
        # nothing above an unfinished task is finished either
        if node.recurrence is not None:
            _bounce_recurrence(connection, node, stamp)
            break

        _set_completed(connection, [node], stamp)
        completed.add(node.id)


@event.listens_for(Todo, "before_insert")
@event.listens_for(Todo, "before_update")
def clear_due_for_recurrence(mapper, connection, todo: Todo):
    """
    A recurring todo carries no deadline, only the day it next comes round

    Nothing that repeats is owed by a date: what it has is the next time it is
    meant to be done, which is what `scheduled` holds. A deadline it was
    carrying before the recurrence was set becomes that first occurrence,
    unless a day was already planned for it, in which case it is dropped.
    """

    if todo.recurrence is None or todo.due is None:
        return

    if todo.scheduled is None:
        todo.scheduled = todo.due

    todo.due = None


@event.listens_for(Todo, "before_update")
def update_scheduled_for_recurrence(mapper, connection, todo: Todo):
    """
    Bounces a ticked-off recurring todo back to pending, one interval on

    A recurring todo is never finished, only done for now: ticking it off
    moves the day it is planned for forward by its interval and hands it
    straight back, pending. The tick never lands and the row never moves,
    which is why the pane flashes it instead.

    Only the tick moves it on, and only the recurrence being set gives it its
    first day. Everything else done to a recurring todo -- its priority, its
    description, its note -- leaves the day it is planned for exactly where it
    was, which it did not when this ran on every update: one that a cascade
    had left completed in the database, or one whose day had been given up to
    a step of its own, had that day walked forward or filled in by the next
    unrelated edit made to it.
    """

    if todo.recurrence is None:
        return

    if not (_changed(todo, "pending") or _changed(todo, "recurrence")):
        return

    if todo.scheduled is None:
        todo.scheduled = datetime.now()

    if todo.pending:
        return

    todo.pending = True
    todo.scheduled += todo.recurrence


def _set_scheduled(
    connection, todos: List[Todo], when: Optional[datetime]
) -> None:
    ids = [todo.id for todo in todos]

    if not ids:
        return

    query = update(Todo).where(Todo.id.in_(ids)).values(scheduled=when)
    connection.execute(query)


@event.listens_for(Todo, "before_insert")
def inherit_scheduled_from_parent(mapper, connection, target: Todo):
    """
    A step added to a task that is planned for a day is planned for it too

    The day belongs to the whole task, so a step written into one joins it
    rather than arriving undated inside work that is already spoken for. A
    step that was given a day of its own on the way in is the other case, and
    is read the way changing one is: the task can no longer claim a day its
    parts do not agree on, so it loses the one it had.
    """

    parent = target.parent_todo

    if parent is None:
        return

    if target.scheduled is None:
        target.scheduled = parent.scheduled
        return

    if target.scheduled != parent.scheduled:
        _set_scheduled(connection, list(_ancestors(target)), None)


@event.listens_for(Todo, "before_update")
def cascade_scheduled(mapper, connection, target: Todo):
    """
    A day put on a todo is the day of everything under it, and of nothing above

    Planning a task plans the whole of it: every step of it, at any depth, is
    moved to the day the task was given, since what was planned is the task
    and not one part of it.

    Planning a single step is the opposite, and says the task no longer
    happens all at once: the step takes the day, and every task it sits
    inside gives its own day up, because a task cannot claim a day its parts
    have stopped agreeing on. Planning the task again puts them all back on
    the same day, which is what makes the two states the only two there are.
    """

    if not _changed(target, "scheduled"):
        return

    _set_scheduled(connection, list(_descendants(target)), target.scheduled)
    _set_scheduled(connection, list(_ancestors(target)), None)
