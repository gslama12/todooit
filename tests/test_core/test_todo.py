from datetime import datetime, timedelta
from pytest import raises
from todooit.api.exceptions import NoParentError, MultipleParentError
from todooit.api import Project, Todo
from tests.test_core.core_base import *  # noqa


def test_todo_creation(create_project, create_todo):
    p = create_project()
    _ = [create_todo(parent_project=p) for _ in range(5)]

    result = Todo.all()
    assert len(result) == 5

    indexs = sorted([t.order_index for t in result])
    assert indexs == [0, 1, 2, 3, 4]


def test_sibling_methods(create_project, create_todo):
    p = create_project()
    _ = [create_todo(parent_project=p) for _ in range(5)]

    todo = Todo.all()[0]
    assert todo is not None

    siblings = todo.siblings
    index_ids = [p.order_index for p in siblings]
    assert index_ids == [0, 1, 2, 3, 4]
    assert siblings[0].is_first_sibling()
    assert siblings[-1].is_last_sibling()


def test_todo_siblings_by_creation(create_project, create_todo):
    p = create_project()
    todo = [create_todo(parent_project=p) for _ in range(5)][0]
    assert len(todo.siblings) == 5


def test_without_parent():
    t = Todo()

    with raises(NoParentError):
        t.save()


def test_with_both_parents(create_todo, create_project):
    with raises(MultipleParentError):
        create_todo(parent_project=create_project(), parent_todo=create_todo())


def test_sibling_add(create_todo):
    t = create_todo()

    t2 = t.add_sibling()
    assert len(t.siblings) == 2
    assert len(t2.siblings) == 2
    assert t2.order_index == 1


def test_nest_level(create_todo):
    t = create_todo()
    assert t.nest_level == 0

    t = t.add_todo()
    assert t.nest_level == 1

    t = t.add_todo()
    assert t.nest_level == 2


def test_from_id(todo1):
    _id = todo1.id
    t_from_id = Todo.from_id(str(_id))
    assert t_from_id == todo1


def test_toggle_complete(todo1):
    assert todo1.pending
    assert todo1.is_pending
    assert not todo1.is_completed

    todo1.toggle_complete()
    assert not todo1.pending
    assert not todo1.is_pending
    assert todo1.is_completed


def test_toggle_complete_parent(create_project, create_todo):
    """A task is ticked by hand, never by its steps running out"""

    p = create_project()
    t = p.add_todo()
    t1 = t.add_todo()
    t2 = t.add_todo()

    t1.toggle_complete()
    assert not t.is_completed

    t2.toggle_complete()
    assert not t.is_completed

    t.toggle_complete()
    assert t.is_completed

    t1.toggle_complete()
    assert not t.is_completed


def test_due_date_util(create_project, create_todo):
    p = create_project()
    t = p.add_todo()
    assert not t.due
    assert not t.is_overdue
    assert t.status == "pending"

    t.due = datetime.now()
    assert t.is_overdue
    assert t.due
    assert t.status == "overdue"

    t.due = datetime.now() - timedelta(days=1)
    assert t.is_overdue
    assert t.status == "overdue"

    t.due = datetime.now() + timedelta(days=1)
    assert not t.is_overdue
    assert t.status == "pending"

    t.toggle_complete()
    assert t.status == "completed"


def test_priority(create_project, create_todo):
    p = create_project()
    t = p.add_todo()
    assert t.priority == 0

    t.set_priority(1)
    assert t.priority == 1

    t.set_priority(3)
    assert t.priority == 3

    t.set_priority(-1)
    assert t.priority == 0

    t.set_priority(9)
    assert t.priority == 3


def test_recurrence_change(create_project, create_todo):
    p = create_project()
    t = p.add_todo()
    t.scheduled = datetime.strptime("2021-01-01", "%Y-%m-%d")
    t.recurrence = timedelta(days=1)
    t.save()
    assert t.scheduled == datetime.strptime("2021-01-01", "%Y-%m-%d")
    t.toggle_complete()
    assert t.scheduled == datetime.strptime("2021-01-02", "%Y-%m-%d")
    assert t.is_pending


def test_recurrence_takes_over_the_due_date(create_project):
    """A deadline becomes the first occurrence, and the column stays clear"""

    p = create_project()
    t = p.add_todo()
    t.due = datetime.strptime("2021-01-01", "%Y-%m-%d")
    t.recurrence = timedelta(weeks=1)
    t.save()

    assert t.due is None
    assert t.scheduled == datetime.strptime("2021-01-01", "%Y-%m-%d")


def test_recurrence_drops_a_due_date_it_cannot_use(create_project):
    """With a day already planned, the deadline is simply dropped"""

    p = create_project()
    t = p.add_todo()
    t.due = datetime.strptime("2021-01-01", "%Y-%m-%d")
    t.scheduled = datetime.strptime("2021-02-01", "%Y-%m-%d")
    t.recurrence = timedelta(weeks=1)
    t.save()

    assert t.due is None
    assert t.scheduled == datetime.strptime("2021-02-01", "%Y-%m-%d")


# ------------------------------------------------------------------
# Behaviour this fork added to the model itself
# ------------------------------------------------------------------


def test_completion_is_stamped(create_project):
    p = create_project()
    t = p.add_todo()
    assert t.completed_at is None

    t.toggle_complete()
    assert t.completed_at is not None

    t.toggle_complete()
    assert t.completed_at is None


def test_agent_toggles(create_project):
    p = create_project()
    t = p.add_todo()
    assert t.agent is False

    t.toggle_agent()
    assert t.agent is True

    t.toggle_agent()
    assert t.agent is False


def test_descendants(create_project):
    p = create_project()
    t = p.add_todo()
    child = t.add_todo()
    grandchild = child.add_todo()
    other = p.add_todo()

    assert t.descendants == [child, grandchild]
    assert other.descendants == []


def test_total_children_counts_only_open_work(create_project):
    """The count trailing a description is the work left, not the row count"""

    p = create_project()
    t = p.add_todo()

    child1 = t.add_todo()
    child1.description = "open step"
    child1.save()

    child2 = t.add_todo()
    child2.description = "done step"
    child2.save()

    grandchild = child1.add_todo()
    grandchild.description = "nested step"
    grandchild.save()

    assert t.total_children == 3

    child2.toggle_complete()
    assert t.total_children == 2

    from todooit.api import move_todo_to_bin

    move_todo_to_bin(child1)
    assert t.total_children == 0


def test_indent_files_under_previous_sibling(create_project):
    p = create_project()
    first = p.add_todo()
    first.description = "first"
    first.save()

    second = p.add_todo()
    second.description = "second"
    second.save()

    assert second.indent() is not None
    assert second.parent_todo == first
    assert second.parent_project is None
    assert first.todos == [second]


def test_indent_carries_steps_along(create_project):
    p = create_project()
    first = p.add_todo()
    second = p.add_todo()
    step = second.add_todo()

    second.indent()
    assert second.parent_todo == first
    assert step.parent_todo == second


def test_indent_with_nothing_above(create_project):
    p = create_project()
    only = p.add_todo()

    assert only.indent() is None
    assert only.parent_project == p


def test_unindent_lands_beside_the_old_parent(create_project):
    # A step on its way out to a project is briefly attached to neither, which
    # a `delete-orphan` cascade on `Todo.todos` used to read as a step nobody
    # wanted: it deleted the row instead of moving it, every sixth `U` or so
    p = create_project()
    first = p.add_todo()
    first.description = "first"
    first.save()

    last = p.add_todo()
    last.description = "last"
    last.save()

    step = first.add_todo()
    step.description = "step"
    step.save()

    assert step.unindent() is not None
    assert step.parent_project == p
    assert step.parent_todo is None

    # Directly under the task it was a step of, not at the end of the run
    ordered = sorted(p.todos, key=lambda t: t.order_index)
    assert [t.description for t in ordered] == ["first", "step", "last"]


def test_unindent_of_a_nested_step(create_project):
    p = create_project()
    task = p.add_todo()
    step = task.add_todo()
    sub_step = step.add_todo()

    assert sub_step.unindent() is not None
    assert sub_step.parent_todo == task


def test_unindent_at_top_level(create_project):
    p = create_project()
    t = p.add_todo()

    assert t.unindent() is None
    assert t.parent_project == p


def test_is_binned(create_project):
    from todooit.api import move_todo_to_bin

    p = create_project()
    t = p.add_todo()
    assert not t.is_binned

    move_todo_to_bin(t)
    assert t.is_binned
    assert t.binned_at is not None


def test_move_to_lands_at_the_end_of_the_new_project(create_project):
    here = create_project()
    there = create_project()

    first = there.add_todo()
    first.description = "already there"
    first.save()

    moved = here.add_todo()
    moved.description = "moved"
    moved.save()

    moved.move_to(there)

    assert moved.parent_project == there
    assert here.todos == []

    ordered = sorted(there.todos, key=lambda t: t.order_index)
    assert [t.description for t in ordered] == ["already there", "moved"]


def test_move_to_carries_the_steps_along(create_project):
    here = create_project()
    there = create_project()

    task = here.add_todo()
    step = task.add_todo()

    task.move_to(there)

    assert task.parent_project == there
    assert step.parent_todo == task
    assert there.todos == [task]


def test_move_to_lifts_a_step_out_of_its_task(create_project):
    here = create_project()
    there = create_project()

    task = here.add_todo()
    task.description = "task"
    task.save()

    step = task.add_todo()
    step.description = "step"
    step.save()

    step.move_to(there)

    assert step.parent_todo is None
    assert step.parent_project == there
    assert task.todos == []


def test_move_to_the_project_a_step_is_already_under(create_project):
    """A step moved into its own project comes out as a task of it"""

    p = create_project()
    task = p.add_todo()
    task.description = "task"
    task.save()

    step = task.add_todo()
    step.description = "step"
    step.save()

    step.move_to(p)

    ordered = sorted(p.todos, key=lambda t: t.order_index)
    assert [t.description for t in ordered] == ["task", "step"]


def test_move_to_leaves_a_binned_todo_binned(create_project):
    from todooit.api import move_todo_to_bin

    here = create_project()
    there = create_project()

    t = here.add_todo()
    move_todo_to_bin(t)

    t.move_to(there)

    assert t.is_binned
    assert t.parent_project == there


def test_from_id_accepts_uuid(create_project, create_todo):
    project = create_project()
    todo = create_todo(parent_project=project)

    assert Todo.from_id(todo.uuid) is todo
    assert Project.from_id(project.uuid) is project


def test_ancestors_nearest_first(create_todo):
    task = create_todo()
    step = create_todo(parent_todo=task)
    sub_step = create_todo(parent_todo=step)

    assert sub_step.ancestors == [step, task]
    assert task.family == [task, step, sub_step]
