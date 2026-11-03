"""
The fixed projects: Today, Upcoming, Completed and the Bin

What each one gathers, the blocks it gathers it into, and the order the
blocks and their rows come in.
"""

from datetime import datetime, timedelta

from tests.test_core.core_base import *  # noqa
from todooit.api import (
    BIN,
    COMPLETED,
    TODAY,
    UPCOMING,
    lifecycle,
    move_todo_to_bin,
)
from todooit.api.fixed_projects import (
    PATH_SEPARATOR,
    fixed_project_from_id,
    fixed_project_from_key,
    fixed_projects,
    project_path,
    split_path,
)


def today_at(hour: int = 10) -> datetime:
    return datetime.now().replace(hour=hour, minute=0, second=0, microsecond=0)


# ------------------------------------------------------------------
# The registry and the helpers around it
# ------------------------------------------------------------------


def test_the_four_fixed_projects_are_registered():
    assert [p.key for p in fixed_projects()] == [
        "today",
        "upcoming",
        "completed",
        "bin",
    ]


def test_fixed_project_lookups(create_project):
    assert fixed_project_from_key("today") is TODAY
    assert fixed_project_from_key("nope") is None

    assert fixed_project_from_id(TODAY.uuid) is TODAY
    assert fixed_project_from_id("Todo_1") is None
    assert fixed_project_from_id(create_project().uuid) is None


def test_fixed_projects_cannot_be_mistaken_for_stored_ones():
    assert TODAY.is_fixed
    assert COMPLETED.pinned_bottom and BIN.pinned_bottom
    assert COMPLETED.muted and BIN.muted
    assert not TODAY.pinned_bottom


def test_project_path(create_project):
    outer = create_project("outer")
    inner = Project(description="inner", parent_project=outer)  # noqa: F405
    inner.save()

    assert project_path(outer) == "outer"
    assert project_path(inner) == f"outer{PATH_SEPARATOR}inner"


# ------------------------------------------------------------------
# Today
# ------------------------------------------------------------------


def test_today_gathers_what_is_scheduled_today(create_project):
    p = create_project("work")

    scheduled = p.add_todo()
    scheduled.description = "today's work"
    scheduled.scheduled = today_at()
    scheduled.save()

    unscheduled = p.add_todo()
    unscheduled.description = "someday"
    unscheduled.save()

    ahead = p.add_todo()
    ahead.scheduled = today_at() + timedelta(days=2)
    ahead.save()

    assert TODAY.todos == [scheduled]


def test_today_leaves_out_finished_and_binned_work(create_project):
    p = create_project("work")

    done = p.add_todo()
    done.scheduled = today_at()
    done.save()
    done.toggle_complete()

    thrown = p.add_todo()
    thrown.scheduled = today_at()
    thrown.save()
    move_todo_to_bin(thrown)

    assert TODAY.todos == []


def test_today_groups_by_project_in_pane_order(create_project):
    first = create_project("first")
    second = create_project("second")

    t2 = second.add_todo()
    t2.scheduled = today_at()
    t2.save()

    t1 = first.add_todo()
    t1.scheduled = today_at()
    t1.save()

    groups = TODAY.todo_groups
    assert [g.label for g in groups] == ["first", "second"]
    assert groups[0].todos == [t1]
    assert groups[1].todos == [t2]


def test_today_orders_a_block_by_priority(create_project):
    p = create_project("work")

    low = p.add_todo()
    low.scheduled = today_at()
    low.priority = 3
    low.save()

    none = p.add_todo()
    none.scheduled = today_at()
    none.save()

    high = p.add_todo()
    high.scheduled = today_at()
    high.priority = 1
    high.save()

    (group,) = TODAY.todo_groups
    assert group.todos == [high, low, none]


def test_today_gathers_a_scheduled_task_with_its_days_steps(create_project):
    """A task planned for today brings the steps that took its day along"""

    p = create_project("work")

    task = p.add_todo()
    task.description = "task"
    step = task.add_todo()
    step.description = "step"
    deeper = step.add_todo()
    deeper.description = "deeper"

    lifecycle.schedule(task, today_at())

    # The day reached the whole family: each of them is today's work, drawn
    # once, where it belongs
    assert step.scheduled == task.scheduled
    assert deeper.scheduled == task.scheduled

    assert sorted(t.id for t in TODAY.todos) == sorted([task.id, step.id, deeper.id])

    (group,) = TODAY.todo_groups
    assert shape(group.rows) == [
        ("task", False, [("step", False, [("deeper", False, [])])]),
    ]


def test_today_draws_a_scheduled_step_under_its_task(create_project):
    """The task comes along for context, with only the day's step under it"""

    p = create_project("work")

    task = p.add_todo()
    task.description = "tax return"
    task.save()

    step = task.add_todo()
    step.description = "dig out the receipts"
    step.scheduled = today_at()
    step.save()

    other = task.add_todo()
    other.description = "fill in the form"
    other.save()

    (group,) = TODAY.todo_groups
    assert group.label == "work"

    # The day's work is the step alone
    assert group.todos == [step]

    # ...drawn under the task it belongs to, which is only there to say so
    (top,) = group.rows
    assert top.todo == task
    assert top.is_context

    (under,) = top.under
    assert under.todo == step
    assert not under.is_context
    assert other not in [row.todo for row in top.under]


def test_context_reaches_all_the_way_up_to_the_task(create_project):
    """Every task above a planned step is drawn, not just the nearest one"""

    p = create_project("work")

    task = p.add_todo()
    part = task.add_todo()
    step = part.add_todo()

    step.scheduled = today_at()
    step.save()

    (group,) = TODAY.todo_groups

    (top,) = group.rows
    assert (top.todo, top.is_context) == (task, True)

    (middle,) = top.under
    assert (middle.todo, middle.is_context) == (part, True)

    (bottom,) = middle.under
    assert (bottom.todo, bottom.is_context) == (step, False)


def test_two_steps_of_one_task_share_its_context_row(create_project):
    """A task is drawn once a block, however much of it lands in that block"""

    p = create_project("work")

    task = p.add_todo()
    first = task.add_todo()
    second = task.add_todo()

    for step in (first, second):
        step.scheduled = today_at()
        step.save()

    (group,) = TODAY.todo_groups

    (top,) = group.rows
    assert top.todo == task
    assert [row.todo for row in top.under] == [first, second]


def test_a_context_row_is_not_part_of_the_days_work(create_project):
    """It is drawn, but nothing about it is what the day asked for"""

    p = create_project("work")

    task = p.add_todo()
    step = task.add_todo()
    step.scheduled = today_at()
    step.save()

    assert TODAY.todos == [step]


def test_today_headings_carry_the_project_path(create_project):
    outer = create_project("outer")
    inner = Project(description="inner", parent_project=outer)  # noqa: F405
    inner.save()

    t = inner.add_todo()
    t.scheduled = today_at()
    t.save()

    (group,) = TODAY.todo_groups
    assert group.label == f"outer{PATH_SEPARATOR}inner"


# ------------------------------------------------------------------
# Upcoming
# ------------------------------------------------------------------


def test_upcoming_gathers_the_days_from_today_on_in_order(create_project):
    """Today opens it: the day being rescheduled off has to be in reach"""

    p = create_project("work")

    later = p.add_todo()
    later.scheduled = today_at() + timedelta(days=5)
    later.save()

    soon = p.add_todo()
    soon.scheduled = today_at() + timedelta(days=2)
    soon.save()

    today = p.add_todo()
    today.scheduled = today_at()
    today.save()

    gone = p.add_todo()
    gone.scheduled = today_at() - timedelta(days=1)
    gone.save()

    # No block for the day that has gone by: what was left on it leads today's
    groups = UPCOMING.todo_groups
    assert [g.todos for g in groups] == [[gone, today], [soon], [later]]


def test_upcoming_names_today_and_tomorrow(create_project):
    p = create_project("work")

    now = p.add_todo()
    now.scheduled = today_at()
    now.save()

    t = p.add_todo()
    t.scheduled = today_at() + timedelta(days=1)
    t.save()

    assert [g.label for g in UPCOMING.todo_groups] == ["Today", "Tomorrow"]


def test_upcoming_gathers_a_scheduled_task_with_its_days_steps(create_project):
    """The same rule Today reads by: a planned task's steps come with it"""

    p = create_project("work")

    task = p.add_todo()
    task.description = "task"
    step = task.add_todo()
    step.description = "step"

    lifecycle.schedule(task, today_at() + timedelta(days=1))

    assert step.scheduled == task.scheduled

    (group,) = UPCOMING.todo_groups
    assert shape(group.rows) == [("task", False, [("step", False, [])])]


def test_upcoming_draws_a_task_over_every_day_it_has_work_in(create_project):
    """A task spread over the week is context in each of the days it touches"""

    p = create_project("work")

    task = p.add_todo()
    now = task.add_todo()
    later = task.add_todo()

    now.scheduled = today_at()
    now.save()

    later.scheduled = today_at() + timedelta(days=1)
    later.save()

    today_block, tomorrow_block = UPCOMING.todo_groups
    assert [g.label for g in (today_block, tomorrow_block)] == [
        "Today",
        "Tomorrow",
    ]

    for block, step in ((today_block, now), (tomorrow_block, later)):
        (top,) = block.rows
        assert (top.todo, top.is_context) == (task, True)
        assert [row.todo for row in top.under] == [step]


# ------------------------------------------------------------------
# Work that slipped: a day that was planned for and has gone by
# ------------------------------------------------------------------


def test_a_todo_slips_once_the_day_it_was_planned_for_has_gone_by(create_project):
    p = create_project("work")

    slipped = p.add_todo()
    slipped.scheduled = today_at() - timedelta(days=2)
    slipped.save()

    # The day is what counts and not the hour: work planned for this morning
    # is still today's work for the rest of the day
    this_morning = p.add_todo()
    this_morning.scheduled = today_at(1)
    this_morning.save()

    someday = p.add_todo()
    someday.save()

    assert slipped.is_overscheduled
    assert not this_morning.is_overscheduled
    assert not someday.is_overscheduled

    # Nothing that is finished with has a day left to miss
    slipped.toggle_complete()
    assert not slipped.is_overscheduled


def test_today_carries_what_slipped_into_it(create_project):
    """A day nobody got to is today's problem, not last week's"""

    p = create_project("work")

    slipped = p.add_todo()
    slipped.description = "meant to do this on monday"
    slipped.scheduled = today_at() - timedelta(days=3)
    slipped.save()

    planned = p.add_todo()
    planned.scheduled = today_at()
    planned.save()

    assert TODAY.todos == [slipped, planned]


def test_today_reads_what_slipped_ahead_of_the_days_own_work(create_project):
    """What has already been missed is the first thing the day decides about"""

    p = create_project("work")

    urgent_today = p.add_todo()
    urgent_today.scheduled = today_at()
    urgent_today.priority = 1
    urgent_today.save()

    slipped = p.add_todo()
    slipped.scheduled = today_at() - timedelta(days=1)
    slipped.save()

    urgent_slipped = p.add_todo()
    urgent_slipped.scheduled = today_at() - timedelta(days=4)
    urgent_slipped.priority = 1
    urgent_slipped.save()

    # Both runs read by priority, and the whole of what slipped comes first
    (group,) = TODAY.todo_groups
    assert group.todos == [urgent_slipped, slipped, urgent_today]


def test_nothing_finished_or_thrown_away_slips_into_today(create_project):
    p = create_project("work")

    done = p.add_todo()
    done.scheduled = today_at() - timedelta(days=2)
    done.save()
    done.toggle_complete()

    thrown = p.add_todo()
    thrown.scheduled = today_at() - timedelta(days=2)
    thrown.save()
    move_todo_to_bin(thrown)

    assert TODAY.todos == []
    assert UPCOMING.todos == []


def test_upcoming_opens_a_today_block_for_what_slipped(create_project):
    """A day gone by is no day to plan against, so nothing is grouped under one"""

    p = create_project("work")

    slipped = p.add_todo()
    slipped.scheduled = today_at() - timedelta(days=6)
    slipped.save()

    (group,) = UPCOMING.todo_groups
    assert group.label == "Today"
    assert group.todos == [slipped]


def test_upcoming_draws_a_slipped_step_under_its_task_in_today(create_project):
    """A step left behind is carried in the way a step of any other day is"""

    p = create_project("work")

    task = p.add_todo()

    missed = task.add_todo()
    missed.scheduled = today_at() - timedelta(days=2)
    missed.save()

    ahead = task.add_todo()
    ahead.scheduled = today_at() + timedelta(days=1)
    ahead.save()

    today_block, tomorrow_block = UPCOMING.todo_groups
    assert [g.label for g in (today_block, tomorrow_block)] == [
        "Today",
        "Tomorrow",
    ]

    for block, step in ((today_block, missed), (tomorrow_block, ahead)):
        (top,) = block.rows
        assert (top.todo, top.is_context) == (task, True)
        assert [row.todo for row in top.under] == [step]


# ------------------------------------------------------------------
# Steps on their own day: each day block lists exactly the
# work planned for that day
# ------------------------------------------------------------------


def tax_return(p, *step_days: int):
    """"Tax return", planned for today, with one step per offset in days"""

    task = p.add_todo()
    task.description = "Tax return"
    task.save()
    lifecycle.schedule(task, today_at())

    steps = []

    for index, days in enumerate(step_days):
        step = task.add_todo()
        step.description = f"step {index}"
        step.save()
        lifecycle.schedule(step, today_at() + timedelta(days=days))
        steps.append(step)

    return task, steps


def shape(rows):
    """The rows of a block as nested (description, is_context, under) tuples"""

    return [
        (row.todo.description, row.is_context, shape(row.under or []))
        for row in rows
    ]


def test_today_shows_a_task_with_only_the_steps_planned_for_today(create_project):
    p = create_project("work")
    tax_return(p, 0, 1, 3)

    (group,) = TODAY.todo_groups

    assert shape(group.rows) == [
        ("Tax return", False, [("step 0", False, [])]),
    ]


def test_today_shows_a_task_alone_when_none_of_its_steps_are_today(create_project):
    p = create_project("work")
    tax_return(p, 1, 2)

    (group,) = TODAY.todo_groups

    assert shape(group.rows) == [("Tax return", False, [])]
    assert [t.description for t in group.todos] == ["Tax return"]


def test_today_draws_a_slipped_ancestor_as_work_and_an_unscheduled_one_as_context(
    create_project,
):
    """
    "Garden season" was planned for last week and is still open, so it is
    carried-over work; "Beds" was never planned, so it only says where the
    day's step belongs
    """

    p = create_project("home")

    garden = p.add_todo()
    garden.description = "Garden season"
    garden.save()
    lifecycle.schedule(garden, today_at() - timedelta(days=7))

    beds = garden.add_todo()
    beds.description = "Beds"
    beds.save()
    lifecycle.schedule(beds, None)

    # Straight to the rows: the step took its parent's day when it was placed
    beds.scheduled = None
    beds.save()

    weed = beds.add_todo()
    weed.description = "Weed"
    weed.save()
    lifecycle.schedule(weed, today_at())

    (group,) = TODAY.todo_groups

    assert shape(group.rows) == [
        ("Garden season", False, [("Beds", True, [("Weed", False, [])])]),
    ]


def test_upcoming_draws_a_task_as_context_on_each_later_day_its_steps_fall_on(
    create_project,
):
    p = create_project("work")
    tax_return(p, 0, 1, 3, 3)

    today_block, tomorrow_block, later_block = UPCOMING.todo_groups

    assert shape(today_block.rows) == [
        ("Tax return", False, [("step 0", False, [])]),
    ]
    assert shape(tomorrow_block.rows) == [
        ("Tax return", True, [("step 1", False, [])]),
    ]
    assert shape(later_block.rows) == [
        ("Tax return", True, [("step 2", False, []), ("step 3", False, [])]),
    ]


def test_upcoming_draws_every_ancestor_of_a_later_step_as_context(create_project):
    """Even one planned itself, when that plan is for an earlier day"""

    p = create_project("work")
    task, (part,) = tax_return(p, 1)

    step = part.add_todo()
    step.description = "sign it"
    step.save()
    lifecycle.schedule(step, today_at() + timedelta(days=2))

    blocks = UPCOMING.todo_groups

    assert [shape(block.rows) for block in blocks] == [
        [("Tax return", False, [])],
        [("Tax return", True, [("step 0", False, [])])],
        [("Tax return", True, [("step 0", True, [("sign it", False, [])])])],
    ]


# ------------------------------------------------------------------
# Completed
# ------------------------------------------------------------------


def test_completed_is_a_log_of_finished_tasks(create_project):
    p = create_project("work")

    first_done = p.add_todo()
    first_done.toggle_complete()
    first_done.completed_at = datetime.now() - timedelta(hours=2)
    first_done.save()

    last_done = p.add_todo()
    last_done.toggle_complete()

    still_open = p.add_todo()
    still_open.save()

    # The most recently finished first, and nothing that is still open
    assert COMPLETED.todos == [last_done, first_done]


def test_completed_shows_a_step_finished_on_its_own_as_its_own_row(create_project):
    """A finished step of an unfinished task leaves for the log like any task"""

    p = create_project("work")
    task = p.add_todo()
    step = task.add_todo()
    task.add_todo()

    step.toggle_complete()

    assert COMPLETED.todos == [step]
    assert task.is_pending

    # Once the task itself is ticked, it carries the step in its own row
    task.toggle_complete()

    assert COMPLETED.todos == [task]


def test_completed_leaves_out_the_binned(create_project):
    p = create_project("work")
    t = p.add_todo()
    t.toggle_complete()
    move_todo_to_bin(t)

    assert COMPLETED.todos == []


# ------------------------------------------------------------------
# Bin
# ------------------------------------------------------------------


def test_bin_is_a_log_of_thrown_away_tasks(create_project):
    p = create_project("work")

    first_out = p.add_todo()
    move_todo_to_bin(first_out)
    first_out.binned_at = datetime.now() - timedelta(hours=2)
    first_out.save()

    last_out = p.add_todo()
    move_todo_to_bin(last_out)

    kept = p.add_todo()
    kept.save()

    assert BIN.todos == [last_out, first_out]
    assert kept not in BIN.todos


def test_bin_shows_a_task_with_its_steps_inside_it(create_project):
    p = create_project("work")
    task = p.add_todo()
    task.add_todo()

    move_todo_to_bin(task)

    # One row: the task. The step is drawn under it, not beside it.
    assert BIN.todos == [task]


# ------------------------------------------------------------------
# Work planned before a day meant the whole of a task
# ------------------------------------------------------------------


def test_upcoming_draws_no_step_twice(create_project):
    """
    A step on a later day than its task is listed on that day only (story 48)

    The task is today's work and alone there; tomorrow it is just the context
    the step needs.
    """

    p = create_project("work")
    task, (step,) = tax_return(p, 1)

    today_block, tomorrow_block = UPCOMING.todo_groups

    assert shape(today_block.rows) == [("Tax return", False, [])]
    assert shape(tomorrow_block.rows) == [("Tax return", True, [("step 0", False, [])])]

    drawn = [todo.id for group in UPCOMING.todo_groups for todo in group.todos]
    assert drawn == [task.id, step.id]


def test_split_path_reads_either_separator():
    assert split_path("outer/inner") == ["outer", "inner"]
    assert split_path("outer › inner") == ["outer", "inner"]
    assert split_path(" ") == []
