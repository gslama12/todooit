from datetime import datetime, timedelta

from tests.test_core.core_base import *  # noqa


def test_todo_status_update_children(todo1):
    assert todo1.is_pending

    for child_todo in todo1.todos:
        child_todo.toggle_complete()

    assert not todo1.is_pending


def test_ticking_the_last_step_ticks_the_whole_chain(create_project):
    """Finishing the final step of the final part finishes the whole task"""

    p = create_project()
    task = p.add_todo()
    part = task.add_todo()
    step1 = part.add_todo()
    step2 = part.add_todo()

    step1.toggle_complete()
    assert part.is_pending
    assert task.is_pending

    step2.toggle_complete()
    assert part.is_completed
    assert task.is_completed


def test_ticking_a_parent_ticks_everything_underneath(create_project):
    p = create_project()
    task = p.add_todo()
    step = task.add_todo()
    sub_step = step.add_todo()

    task.toggle_complete()

    assert step.is_completed
    assert sub_step.is_completed


def test_family_shares_one_completion_stamp(create_project):
    """The moment the last step was done is the moment the task was done"""

    p = create_project()
    task = p.add_todo()
    step = task.add_todo()

    task.toggle_complete()

    assert task.completed_at is not None
    assert step.completed_at == task.completed_at


def test_unticking_a_step_unticks_every_ancestor(create_project):
    p = create_project()
    task = p.add_todo()
    part = task.add_todo()
    step = part.add_todo()

    task.toggle_complete()
    assert task.is_completed

    step.toggle_complete()

    assert step.is_pending
    assert part.is_pending
    assert task.is_pending


def test_unticking_a_task_unticks_its_steps(create_project):
    """A task is undone the moment any part of it is"""

    p = create_project()
    task = p.add_todo()
    step1 = task.add_todo()
    step2 = task.add_todo()

    task.toggle_complete()
    assert step1.is_completed and step2.is_completed

    task.toggle_complete()

    assert step1.is_pending
    assert step2.is_pending


def test_unticking_leaves_finished_siblings_alone(create_project):
    """Unticking one step does not undo the work beside it"""

    p = create_project()
    task = p.add_todo()
    step1 = task.add_todo()
    step2 = task.add_todo()

    step1.toggle_complete()
    step2.toggle_complete()
    assert task.is_completed

    step1.toggle_complete()

    assert task.is_pending
    assert step2.is_completed


def test_recurrence_forces_pending(create_project):
    """Setting a recurrence on a finished todo hands it back as work"""

    p = create_project()
    t = p.add_todo()
    t.toggle_complete()
    assert t.is_completed

    t.recurrence = timedelta(days=7)
    t.save()

    assert t.is_pending


def test_completing_recurring_todo_bounces_it_forward(create_project):
    p = create_project()
    t = p.add_todo()
    t.scheduled = datetime(2026, 1, 1)
    t.recurrence = timedelta(days=3)
    t.save()

    t.toggle_complete()

    assert t.is_pending
    assert t.scheduled == datetime(2026, 1, 4)
    assert t.completed_at is None


def test_completing_recurring_todo_without_a_date_schedules_it(create_project):
    """A recurring todo with no day planned starts counting from now"""

    p = create_project()
    t = p.add_todo()
    t.recurrence = timedelta(days=1)
    t.save()

    before = datetime.now()
    t.toggle_complete()

    assert t.is_pending
    assert t.scheduled is not None
    assert t.scheduled >= before


def test_editing_a_recurring_todo_leaves_its_day_alone(create_project, session):
    """Only the tick moves a recurring todo on, not any other edit"""

    p = create_project()
    t = p.add_todo()
    t.scheduled = datetime(2026, 1, 1)
    t.recurrence = timedelta(days=3)
    t.save()

    t.set_priority(3)
    t.description = "renamed"
    t.save()

    assert t.scheduled == datetime(2026, 1, 1)
    assert t.is_pending


def test_editing_a_recurring_todo_with_no_day_leaves_it_undated(
    create_project, session
):
    """A recurring task whose day went to a step of its own stays undated"""

    p = create_project()
    task = p.add_todo()
    task.scheduled = datetime(2026, 5, 1)
    task.recurrence = timedelta(days=7)
    task.save()

    step = task.add_todo()
    step.scheduled = datetime(2026, 6, 2)
    step.save()
    session.expire_all()
    assert task.scheduled is None

    task.set_priority(2)
    session.expire_all()

    assert task.scheduled is None
    assert step.scheduled == datetime(2026, 6, 2)


def test_last_step_bounces_the_recurring_task_it_finishes(
    create_project, session
):
    """A repeating task carried off by its last step comes round again there"""

    p = create_project()
    task = p.add_todo()
    task.scheduled = datetime(2026, 1, 1)
    task.recurrence = timedelta(days=3)
    task.save()

    step = task.add_todo()
    step.save()

    step.toggle_complete()
    session.expire_all()

    assert task.is_pending
    assert task.completed_at is None
    assert task.scheduled == datetime(2026, 1, 4)

    task.set_priority(1)
    session.expire_all()

    assert task.scheduled == datetime(2026, 1, 4)


def test_a_bounced_task_does_not_finish_the_task_above_it(
    create_project, session
):
    """Nothing above a task that has come round again is finished either"""

    p = create_project()
    outer = p.add_todo()
    task = outer.add_todo()
    task.recurrence = timedelta(days=3)
    task.save()

    step = task.add_todo()
    step.save()

    step.toggle_complete()
    session.expire_all()

    assert task.is_pending
    assert outer.is_pending


def test_ticking_a_task_bounces_the_repeating_steps_inside_it(
    create_project, session
):
    """A step that repeats is moved on rather than carried off finished"""

    p = create_project()
    task = p.add_todo()
    task.save()

    step = task.add_todo()
    step.scheduled = datetime(2026, 2, 1)
    step.recurrence = timedelta(days=1)
    step.save()

    plain = task.add_todo()
    plain.save()

    task.toggle_complete()
    session.expire_all()

    assert plain.is_completed
    assert step.is_pending
    assert step.scheduled == datetime(2026, 2, 2)

    step.set_priority(1)
    session.expire_all()

    assert step.scheduled == datetime(2026, 2, 2)


# ------------------------------------------------------------------
# The day a task is planned for, and the days its steps are
# ------------------------------------------------------------------


def _at(days: int = 0) -> datetime:
    return datetime.now().replace(
        hour=9, minute=0, second=0, microsecond=0
    ) + timedelta(days=days)


def test_planning_a_task_plans_every_step_of_it(create_project):
    """The day belongs to the whole task, at any depth"""

    p = create_project()
    task = p.add_todo()
    step = task.add_todo()
    sub_step = step.add_todo()

    day = _at()
    task.scheduled = day
    task.save()

    assert step.scheduled == day
    assert sub_step.scheduled == day


def test_a_step_added_to_a_planned_task_joins_it(create_project):
    """Nothing arrives undated inside work that is already spoken for"""

    p = create_project()
    task = p.add_todo()
    task.scheduled = _at()
    task.save()

    assert task.add_todo().scheduled == task.scheduled


def test_planning_a_step_takes_the_day_off_its_task(create_project):
    """A task cannot claim a day its parts have stopped agreeing on"""

    p = create_project()
    task = p.add_todo()
    part = task.add_todo()
    step = part.add_todo()
    other = task.add_todo()

    task.scheduled = _at()
    task.save()

    step.scheduled = _at(1)
    step.save()

    # Everything the step sits inside gives its day up, all the way to the top
    assert step.scheduled == _at(1)
    assert part.scheduled is None
    assert task.scheduled is None

    # What the step is not part of keeps the day the task handed out
    assert other.scheduled == _at()


def test_planning_the_task_again_puts_its_steps_back_on_one_day(create_project):
    """The two states are the only two there are"""

    p = create_project()
    task = p.add_todo()
    first = task.add_todo()
    second = task.add_todo()

    task.scheduled = _at()
    task.save()

    first.scheduled = _at(3)
    first.save()
    assert task.scheduled is None

    task.scheduled = _at(1)
    task.save()

    assert first.scheduled == _at(1)
    assert second.scheduled == _at(1)


def test_clearing_a_task_clears_its_steps(create_project):
    """Taking the day off a task takes it off the work the task handed it to"""

    p = create_project()
    task = p.add_todo()
    step = task.add_todo()

    task.scheduled = _at()
    task.save()

    task.scheduled = None
    task.save()

    assert step.scheduled is None


def test_a_step_created_with_a_day_of_its_own_frees_its_task(create_project):
    """The same rule, read on the way in rather than on a change"""

    p = create_project()
    task = p.add_todo()
    task.scheduled = _at()
    task.save()

    step = task.add_todo()
    step.scheduled = _at(2)
    step.save()

    assert task.scheduled is None
    assert step.scheduled == _at(2)


def test_a_task_in_a_project_never_reaches_out_of_it(create_project):
    """Only todos inherit: a project is not a step of anything"""

    p = create_project()
    first = p.add_todo()
    second = p.add_todo()

    first.scheduled = _at()
    first.save()

    assert second.scheduled is None


def test_a_step_written_in_with_its_own_day_frees_its_task(create_project):
    """A step that never agreed with its task, from the moment it was made"""

    p = create_project()
    task = p.add_todo()
    task.scheduled = _at()
    task.save()

    step = Todo(parent_todo=task, scheduled=_at(2))  # noqa: F405
    step.save()

    assert task.scheduled is None
    assert step.scheduled == _at(2)
