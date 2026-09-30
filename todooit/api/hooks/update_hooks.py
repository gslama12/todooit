from datetime import datetime
from typing import List
from sqlalchemy import event, inspect, update
from ..todo import Todo


def _bulk_update(connection, todos: List[Todo], **values) -> None:
    """
    Write `values` straight to the given rows, bypassing the ORM (and these hooks)
    """

    ids = [todo.id for todo in todos]

    if not ids:
        return

    connection.execute(update(Todo).where(Todo.id.in_(ids)).values(**values))


def _set_pending(connection, todos: List[Todo]) -> None:
    _bulk_update(connection, todos, pending=True, completed_at=None)


def _bounce_recurrence(connection, todo: Todo, stamp: datetime) -> None:
    """
    Move a recurring todo one interval on and set it (and its children) pending
    """

    assert todo.recurrence is not None

    when = (todo.scheduled or stamp) + todo.recurrence
    _bulk_update(connection, [todo], pending=True, completed_at=None, scheduled=when)
    _set_pending(connection, todo.descendants)


def _complete(connection, todos: List[Todo], stamp: datetime) -> None:
    """
    Complete the todos; recurring ones are bounced to their next occurrence instead
    """

    _bulk_update(
        connection,
        [todo for todo in todos if todo.recurrence is None],
        pending=False,
        completed_at=stamp,
    )

    for todo in todos:
        if todo.recurrence is not None:
            _bounce_recurrence(connection, todo, stamp)


def _changed(todo: Todo, field: str) -> bool:
    return inspect(todo).attrs[field].history.has_changes()


@event.listens_for(Todo, "before_update")
def update_children_to_pending(_, connection, target: Todo):
    """
    Unticking a todo unticks all its descendants

    Only on the untick itself, not on any later edit of a pending todo.
    """

    if not target.pending or not _changed(target, "pending"):
        return

    _set_pending(connection, target.descendants)


@event.listens_for(Todo, "before_update")
def update_children_to_completed(_, connection, target: Todo):
    """
    Ticking a todo ticks all its descendants
    """

    if target.pending:
        return

    stamp = target.completed_at or datetime.now()
    _complete(connection, target.descendants, stamp)


@event.listens_for(Todo, "before_update")
def update_parent_to_pending(mapper, connection, target: Todo):
    """
    A pending todo makes all its ancestors pending
    """

    if not target.pending or not target.parent_todo:
        return

    _set_pending(connection, target.ancestors)


@event.listens_for(Todo, "before_insert")
@event.listens_for(Todo, "before_update")
def clear_due_for_recurrence(mapper, connection, todo: Todo):
    """
    Recurring todos have no due date: it becomes the scheduled date (if unset)
    """

    if todo.recurrence is None or todo.due is None:
        return

    if todo.scheduled is None:
        todo.scheduled = todo.due

    todo.due = None


@event.listens_for(Todo, "before_update")
def update_scheduled_for_recurrence(mapper, connection, todo: Todo):
    """
    Ticking a recurring todo moves it one interval on and keeps it pending

    Only runs when `pending` or `recurrence` changed, so unrelated edits never
    move the schedule.
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

    # The completion cascade already ticked the children; hand them back fresh
    _set_pending(connection, todo.descendants)


@event.listens_for(Todo, "before_insert")
def inherit_scheduled_from_parent(mapper, connection, target: Todo):
    """
    A new child inherits its parent's scheduled date

    If it arrives with a different date, its ancestors lose theirs instead.
    """

    parent = target.parent_todo

    if parent is None:
        return

    if target.scheduled is None:
        target.scheduled = parent.scheduled
        return

    if target.scheduled != parent.scheduled:
        _bulk_update(connection, target.ancestors, scheduled=None)


@event.listens_for(Todo, "before_update")
def cascade_scheduled(mapper, connection, target: Todo):
    """
    Scheduling a todo schedules all its descendants and unschedules its ancestors
    """

    if not _changed(target, "scheduled"):
        return

    _bulk_update(connection, target.descendants, scheduled=target.scheduled)
    _bulk_update(connection, target.ancestors, scheduled=None)
