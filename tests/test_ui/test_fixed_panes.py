"""
The panes of the fixed projects: what they draw, and what they turn away
"""


import sys
from datetime import date, datetime, timedelta

import pytest
from rich.style import Style as RichStyle
from rich.styled import Styled
from textual.style import Style

from tests.test_ui.ui_base import (
    boot,
    commit_line,
    create_and_move_to_todo,
    descriptions,
    flashed,
    new_project,
    new_todo,
    notification_message,
    reveal_project,
    run_pilot,
    tree_options,
    visible_todos,
)
from todooit.api import TODAY, UPCOMING, Todo, move_project_to_bin, restore_todo
from todooit.ui.api.events import GotoFixedProject, SpawnHelp
from todooit.ui.pane_layout import GUIDE_BLANK, GUIDE_LAST_BRANCH, context_id
from todooit.ui.widgets.trees.fixed_todos_tree import reschedule_mark


async def settle(pilot):
    """
    Waits out the jump a key sends the app on

    Unticking in the log and restoring from the Bin both post the task on to
    the screen, which opens the pane it went to and puts the cursor there. The
    pane can have to be built first, so more than one beat passes before the
    screen is the one the user ends up looking at.
    """

    for _ in range(5):
        await pilot.pause()


async def schedule(pilot, when: str):
    """Schedules the highlighted todo by typing into the `s` edit"""

    await pilot.press("s")
    await commit_line(pilot, when)


def slipped_mark(days: int = 1) -> str:
    """What a row planned that many days back is expected to lead with"""

    return reschedule_mark(datetime.now() - timedelta(days=days))


def drawn_segments(tree, option):
    """
    What a row actually comes out as: its first line, as (text, color) pairs
    """

    (strip, *_) = tree._get_option_render(option, Style())

    return [
        (
            segment.text,
            segment.style.color.triplet.hex.lower()
            if segment.style and segment.style.color and segment.style.color.triplet
            else None,
        )
        for segment in strip
    ]


def context_ids(tree):
    """The rows the pane drew only to say what the work belongs to"""

    return [
        o.id
        for o in tree._options
        if (o.id or "").startswith("todooit-todo-context-")
    ]


async def test_today_draws_a_block_per_project():
    async with run_pilot() as pilot:
        app = await boot(pilot)

        await new_project(pilot, "home")
        await new_todo(pilot, "water plants")
        await schedule(pilot, "today")

        await new_project(pilot, "work")
        await new_todo(pilot, "write report")
        await schedule(pilot, "today")

        await pilot.press("g", "t")
        await pilot.pause()

        tree = visible_todos(app)
        rows = tree_options(tree)
        assert len(rows) == 2

        # A heading per project stands over the rows (headings are furniture,
        # so they show up as static rows between the stored ones)
        headings = [
            _id
            for _id in (o.id for o in tree._options)
            if _id and _id.startswith("todooit-todo-group")
        ]
        assert len(headings) == 2


async def test_today_hides_the_scheduled_column():
    async with run_pilot() as pilot:
        app = await boot(pilot)

        await create_and_move_to_todo(pilot)
        await pilot.press("n")
        await commit_line(pilot, "planned")
        await schedule(pilot, "today")

        await pilot.press("g", "t")
        await pilot.pause()

        today_tree = visible_todos(app)
        columns = [item.value for item in today_tree.render_layout]

        assert "scheduled" not in columns
        assert "scheduled" in today_tree.editable_columns


async def test_today_opens_the_steps_of_a_scheduled_task():
    """A scheduled task brings its steps along, and `h` folds them away"""

    async with run_pilot() as pilot:
        app = await boot(pilot)

        await create_and_move_to_todo(pilot)
        await pilot.press("n")
        await commit_line(pilot, "task")
        await pilot.press("N")
        await commit_line(pilot, "step")

        # Only the task is given a date; the step has none of its own
        await pilot.press("k")
        await pilot.pause()
        await schedule(pilot, "today")

        await pilot.press("g", "t")
        await pilot.pause()

        today = visible_todos(app)
        assert descriptions(today) == ["task", "step"]

        await pilot.press("h")
        await pilot.pause()
        assert descriptions(today) == ["task"]

        await pilot.press("h")
        await pilot.pause()
        assert descriptions(today) == ["task", "step"]


async def test_today_draws_the_task_above_a_scheduled_step():
    """The task is drawn for context; the day's work is the step alone"""

    async with run_pilot() as pilot:
        app = await boot(pilot)

        await create_and_move_to_todo(pilot)
        await pilot.press("n")
        await commit_line(pilot, "task")
        await pilot.press("N")
        await commit_line(pilot, "step")
        await schedule(pilot, "today")

        task = Todo.from_id("Todo_1")
        assert task.description == "task"
        assert task.scheduled is None

        await pilot.press("g", "t")
        await pilot.pause()

        today = visible_todos(app)
        assert descriptions(today) == ["step"]
        assert context_ids(today) == [context_id(0, task)]

        # The cursor opens on the work and cannot be walked onto the context
        assert today.current_model.description == "step"

        await pilot.press("k")
        await pilot.pause()
        assert today.current_model.description == "step"


async def test_a_guide_ends_at_the_last_row_the_pane_drew():
    """
    The elbow follows the rows on screen, not the ones in the project

    A context row shows only the work the day asked for, so the step that ends
    a family here is rarely the one that ends it where it is filed.
    """

    async with run_pilot() as pilot:
        app = await boot(pilot)

        await create_and_move_to_todo(pilot)
        await pilot.press("n")
        await commit_line(pilot, "task")

        await pilot.press("N")
        await commit_line(pilot, "planned")
        await schedule(pilot, "today")

        # Filed after it, and not part of today: the guide must not point at it
        await pilot.press("n")
        await commit_line(pilot, "someday")

        await pilot.press("g", "t")
        await pilot.pause()

        today = visible_todos(app)
        assert descriptions(today) == ["planned"]

        planned = today.current_model
        assert planned.description == "planned"
        assert not planned.is_last_sibling()

        row = today._rows[planned.uuid]
        assert row.guides == GUIDE_LAST_BRANCH
        assert row.below == GUIDE_BLANK


async def test_upcoming_repeats_a_task_over_the_days_it_has_work_in():
    """One context row per day block, each naming the day it belongs to"""

    async with run_pilot() as pilot:
        app = await boot(pilot)

        await create_and_move_to_todo(pilot)
        await pilot.press("n")
        await commit_line(pilot, "task")

        await pilot.press("N")
        await commit_line(pilot, "now")
        await schedule(pilot, "today")

        await pilot.press("n")
        await commit_line(pilot, "later")
        await schedule(pilot, "tomorrow")

        await pilot.press("g", "u")
        await pilot.pause()

        upcoming = visible_todos(app)
        assert descriptions(upcoming) == ["now", "later"]

        # Drawn twice over, and named after the block rather than the task, so
        # that the two rows are not the same row
        task = Todo.from_id("Todo_1")
        assert context_ids(upcoming) == [
            context_id(0, task),
            context_id(1, task),
        ]


async def plan_tax_return(pilot):
    """"Tax return" planned for today, one step today and one tomorrow"""

    await create_and_move_to_todo(pilot)
    await pilot.press("n")
    await commit_line(pilot, "Tax return")
    await schedule(pilot, "today")

    # Each step takes the task's day when it is added
    await pilot.press("N")
    await commit_line(pilot, "now")

    await pilot.press("n")
    await commit_line(pilot, "later")
    await schedule(pilot, "tomorrow")

    return Todo.from_id("Todo_1")


async def test_today_draws_a_task_planned_today_as_work_with_only_todays_step():
    async with run_pilot() as pilot:
        app = await boot(pilot)
        task = await plan_tax_return(pilot)

        await pilot.press("g", "t")
        await pilot.pause()

        today = visible_todos(app)
        assert descriptions(today) == ["Tax return", "now"]
        assert context_ids(today) == []

        # A regular row, drawn the way any row is, not dimmed as context
        prompt = today.prompt_for(task.uuid)
        assert not (isinstance(prompt, Styled) and prompt.style == "dim")


async def test_upcoming_draws_a_later_step_on_its_day_under_a_dimmed_task():
    async with run_pilot() as pilot:
        app = await boot(pilot)
        task = await plan_tax_return(pilot)

        await pilot.press("g", "u")
        await pilot.pause()

        upcoming = visible_todos(app)

        # Tomorrow's step is not also drawn under the task today
        assert descriptions(upcoming) == ["Tax return", "now", "later"]

        (context,) = context_ids(upcoming)
        assert context == context_id(1, task)

        prompt = upcoming.prompt_for(context)
        assert isinstance(prompt, Styled) and prompt.style == "dim"


async def test_upcoming_opens_with_today():
    """The day being rescheduled off is in reach of the days ahead"""

    async with run_pilot() as pilot:
        app = await boot(pilot)

        await create_and_move_to_todo(pilot)
        await pilot.press("n")
        await commit_line(pilot, "now")
        await schedule(pilot, "today")

        await pilot.press("n")
        await commit_line(pilot, "soon")
        await schedule(pilot, "tomorrow")

        await pilot.press("g", "u")
        await pilot.pause()

        assert descriptions(visible_todos(app)) == ["now", "soon"]


async def test_upcoming_groups_by_day():
    async with run_pilot() as pilot:
        app = await boot(pilot)

        await create_and_move_to_todo(pilot)
        await pilot.press("n")
        await commit_line(pilot, "sooner")
        await schedule(pilot, "tomorrow")

        await pilot.press("n")
        await commit_line(pilot, "later")
        await schedule(pilot, "in 3 days")

        await pilot.press("g", "u")
        await pilot.pause()

        upcoming = visible_todos(app)
        rows = tree_options(upcoming)
        assert [upcoming._renderers[o.id].model.description for o in rows] == [
            "sooner",
            "later",
        ]


async def test_today_marks_the_rows_that_slipped_into_it():
    """A row that was planned for a day gone by says what is to be done with it"""

    async with run_pilot() as pilot:
        app = await boot(pilot)

        await create_and_move_to_todo(pilot)
        await pilot.press("n")
        await commit_line(pilot, "missed")
        await schedule(pilot, "yesterday")

        await pilot.press("n")
        await commit_line(pilot, "planned")
        await schedule(pilot, "today")

        await pilot.press("g", "t")
        await pilot.pause()

        today = visible_todos(app)

        # What slipped leads the block, so it is where the rescheduling starts
        assert descriptions(today) == ["missed", "planned"]

        missed, planned = (today._renderers[o.id].model for o in tree_options(today))
        assert today.row_mark(missed).plain == slipped_mark()

        # And what it says is the day the row was planned for, which is the
        # one thing the pane took off it by carrying it onto today
        assert today.row_mark(missed).plain.strip() == missed.scheduled.strftime(
            "(%d.%m.)"
        )

        # Nothing to say about a row that is where it was planned to be
        assert today.row_mark(planned).plain == ""

        # And nothing added after the description either
        assert today.row_note(missed, today._rows[missed.uuid]).plain == ""


def test_the_mark_is_the_day_the_row_was_planned_for():
    """Day and month, in the German order, with no year to read past"""

    assert reschedule_mark(datetime(2026, 9, 14)) == "(14.09.) "

    # A day out of another month and another year reads the same way: what the
    # mark is for is picking the row off that day again, and a row still being
    # picked off is a row from around now
    assert reschedule_mark(datetime(2025, 3, 1)) == "(01.03.) "

    # The hour it was planned at has no say in it, the way the planning itself
    # has none: it is a day the row slipped off, not a moment
    assert reschedule_mark(datetime(2026, 9, 14, 23, 45)) == "(14.09.) "


async def test_the_mark_leads_the_description_without_coloring_it():
    """In front of the row's own words, in red, and only the mark in red"""

    async with run_pilot() as pilot:
        app = await boot(pilot)

        await create_and_move_to_todo(pilot)
        await pilot.press("n")
        await commit_line(pilot, "missed")
        await schedule(pilot, "yesterday")

        await pilot.press("g", "t")
        await pilot.pause()

        today = visible_todos(app)
        (row,) = tree_options(today)

        red = RichStyle(color=today.api.vars.theme.red).color.triplet.hex.lower()
        segments = drawn_segments(today, row)
        drawn = "".join(text for text, _ in segments)

        assert drawn.index(slipped_mark()) < drawn.index("missed")

        marks = [color for text, color in segments if slipped_mark().strip() in text]
        assert marks == [red]

        # The description behind it is left in the color it came in
        described = [color for text, color in segments if "missed" in text]
        assert described and red not in described


async def test_upcoming_carries_a_slipped_row_into_today():
    """Nothing is filed under a day that has gone by: it is picked again here"""

    async with run_pilot() as pilot:
        app = await boot(pilot)

        await create_and_move_to_todo(pilot)
        await pilot.press("n")
        await commit_line(pilot, "missed")
        await schedule(pilot, "yesterday")

        await pilot.press("n")
        await commit_line(pilot, "soon")
        await schedule(pilot, "tomorrow")

        await pilot.press("g", "u")
        await pilot.pause()

        upcoming = visible_todos(app)
        assert [g.label for g in upcoming.todo_groups] == ["Today", "Tomorrow"]
        assert descriptions(upcoming) == ["missed", "soon"]

        missed, soon = (upcoming._renderers[o.id].model for o in tree_options(upcoming))
        assert upcoming.row_mark(missed).plain == slipped_mark()
        assert upcoming.row_mark(soon).plain == ""

        # The project a row came out of is still the only thing after it
        assert "project" in upcoming.row_note(missed, upcoming._rows[missed.uuid]).plain


async def test_a_step_finished_on_its_own_is_labelled_with_its_project_only():
    """A lone step in the log names the project it came from, never its parent"""

    async with run_pilot() as pilot:
        app = await boot(pilot)

        await create_and_move_to_todo(pilot)
        await pilot.press("n")
        await commit_line(pilot, "move house")
        await pilot.press("N")
        await commit_line(pilot, "book van")

        await pilot.press("c")
        await pilot.pause()

        await pilot.press("g", "c")
        await pilot.pause()

        completed = visible_todos(app)
        assert descriptions(completed) == ["book van"]

        row_id = tree_options(completed)[0].id
        assert row_id is not None

        step = completed._renderers[row_id].model
        note = completed.row_note(step, completed._rows[step.uuid]).plain

        assert "project" in note
        assert "move house" not in note
        assert step.parent_todo is not None and step.parent_todo.is_pending


async def test_completing_a_task_moves_it_to_completed():
    async with run_pilot() as pilot:
        app = await boot(pilot)

        tree = await create_and_move_to_todo(pilot)
        await pilot.press("n")
        await commit_line(pilot, "done deal")

        await pilot.press("c")
        await pilot.pause()

        # Gone from its own pane
        assert tree_options(tree) == []

        await pilot.press("g", "c")
        await pilot.pause()

        completed = visible_todos(app)
        rows = tree_options(completed)
        assert len(rows) == 1
        assert completed.current_model.description == "done deal"


async def test_unticking_in_completed_goes_to_the_task_at_home():
    """The row leaves the log at once, and the cursor goes where it went"""

    async with run_pilot() as pilot:
        app = await boot(pilot)

        tree = await create_and_move_to_todo(pilot)
        await pilot.press("n")
        await commit_line(pilot, "not quite done")
        await pilot.press("c")
        await pilot.pause()

        await pilot.press("g", "c")
        await pilot.pause()

        completed = visible_todos(app)

        with flashed() as flashes:
            await pilot.press("c")  # untick it right there
            await settle(pilot)

        todo = Todo.all()[0]
        assert todo.is_pending

        # Nothing left of it in the log
        assert tree_options(completed) == []

        # The pane in front is the project it came out of, focused, with the
        # cursor on the row and the row flashed the way a found task is
        assert visible_todos(app) is tree
        assert app.focused is tree
        assert tree.current_model is todo
        assert (tree.id, todo.uuid) in flashes

        # And the projects pane came along, so the two sides agree
        assert app.project_tree.current_model is tree.model


async def test_unticking_a_step_in_completed_goes_to_the_step():
    """Unticking a step sends the whole task back, and points at the step"""

    async with run_pilot() as pilot:
        app = await boot(pilot)

        tree = await create_and_move_to_todo(pilot)
        await pilot.press("n")
        await commit_line(pilot, "the task")
        await pilot.press("N")
        await commit_line(pilot, "the step")

        # The task is what gets ticked; the step goes with it
        await pilot.press("k")
        await pilot.press("c")
        await pilot.pause()

        await pilot.press("g", "c")
        await pilot.pause()

        completed = visible_todos(app)

        # The log draws the task with its step under it already open: the
        # cursor starts on the task, and one row down is the step
        await settle(pilot)
        assert completed.current_model.description == "the task"

        await pilot.press("l")
        await pilot.pause()
        assert completed.current_model.description == "the step"

        with flashed() as flashes:
            await pilot.press("c")
            await settle(pilot)

        step = [todo for todo in Todo.all() if todo.description == "the step"][0]

        # The whole family is back among the work to be done
        assert all(todo.is_pending for todo in Todo.all())
        assert tree_options(completed) == []

        assert visible_todos(app) is tree
        assert tree.current_model is step
        assert (tree.id, step.uuid) in flashes


async def test_unticking_a_task_whose_project_was_dropped_rebuilds_it():
    """
    The log can hold a task whose project has since gone to the Bin;
    unticking it rebuilds the project, says so, and goes there
    """

    async with run_pilot() as pilot:
        app = await boot(pilot)

        project = app.api.vars.projects_tree.model.add_project()
        project.description = "abandoned"
        project.save()
        todo = project.add_todo()
        todo.description = "not quite done"
        todo.save()
        todo.toggle_complete()

        move_project_to_bin(project)
        restore_todo(todo)
        app.api.vars.projects_tree.force_refresh()
        await pilot.pause()

        await pilot.press("g", "c")
        await pilot.pause()

        await pilot.press("c")
        await settle(pilot)

        revived = todo.parent_project
        assert todo.is_pending
        assert revived is not None
        assert revived.description == "revived - abandoned"

        assert visible_todos(app).model is revived
        assert visible_todos(app).current_model is todo

        message = notification_message(app)
        assert message is not None and "abandoned" in message


async def test_reticking_in_completed_stays_put():
    """A row that never left the log is not followed anywhere"""

    async with run_pilot() as pilot:
        app = await boot(pilot)

        await create_and_move_to_todo(pilot)
        await pilot.press("n")
        await commit_line(pilot, "done deal")
        await pilot.press("c")
        await pilot.pause()

        await pilot.press("g", "c")
        await pilot.pause()

        completed = visible_todos(app)
        await pilot.press("c")  # untick: off to its own project
        await settle(pilot)

        await pilot.press("c")  # and tick it again, from over there
        await settle(pilot)

        assert Todo.all()[0].is_completed

        # Ticking is not unticking: the cursor stayed in the project's pane
        assert visible_todos(app) is not completed


async def test_fixed_panes_refuse_reordering_and_new_tasks():
    async with run_pilot() as pilot:
        app = await boot(pilot)

        await create_and_move_to_todo(pilot)
        await pilot.press("n")
        await commit_line(pilot, "planned")
        await schedule(pilot, "today")

        await pilot.press("g", "t")
        await pilot.pause()

        for keys, refused in (
            (("n",), "added"),
            (("K",), "reordered"),
            (("L",), "reordered"),
            (("I",), "reordered"),
            (("U",), "reordered"),
        ):
            await pilot.press(*keys)
            await pilot.pause()

            message = notification_message(app)
            assert message is not None and refused in message, keys

        assert len(Todo.all()) == 1


async def test_today_takes_a_new_step_under_a_row():
    """
    `N` in Today files a step under the task, in the task's own project

    Nothing about it is Today's: the step lands exactly where it would have
    from the project's own pane, and joins the day the task is planned for the
    way a step written into a planned task does anywhere else.
    """

    async with run_pilot() as pilot:
        app = await boot(pilot)

        tree = await create_and_move_to_todo(pilot)
        await pilot.press("n")
        await commit_line(pilot, "task")
        await schedule(pilot, "today")

        await pilot.press("g", "t")
        await pilot.pause()

        today = visible_todos(app)
        assert descriptions(today) == ["task"]

        await pilot.press("N")
        await commit_line(pilot, "step")
        await settle(pilot)

        # Drawn under the row it was typed on, with the cursor left on it
        assert descriptions(today) == ["task", "step"]
        assert today.current_model.description == "step"

        task = [todo for todo in Todo.all() if todo.description == "task"][0]
        step = [todo for todo in Todo.all() if todo.description == "step"][0]

        assert step.parent_todo is task
        assert step.parent_project is None

        # The day belongs to the whole task, so the step arrived on it rather
        # than undated inside work that is already spoken for
        assert step.scheduled == task.scheduled

        # And the project it really belongs to has it too, once it is the pane
        # being looked at
        assert descriptions(await reveal_project(pilot, tree.model)) == [
            "task",
            "step",
        ]


async def test_upcoming_takes_a_new_step_under_a_row():
    """A day ahead is a day to break work down on, the same way today is"""

    async with run_pilot() as pilot:
        app = await boot(pilot)

        await create_and_move_to_todo(pilot)
        await pilot.press("n")
        await commit_line(pilot, "task")
        await schedule(pilot, "tomorrow")

        await pilot.press("g", "u")
        await pilot.pause()

        upcoming = visible_todos(app)
        assert descriptions(upcoming) == ["task"]

        await pilot.press("N")
        await commit_line(pilot, "step")
        await settle(pilot)

        assert descriptions(upcoming) == ["task", "step"]

        # One block still, and still tomorrow's: the step joined the day its
        # task was planned for rather than opening a day of its own
        assert [g.label for g in upcoming.todo_groups] == ["Tomorrow"]

        task = [todo for todo in Todo.all() if todo.description == "task"][0]
        step = [todo for todo in Todo.all() if todo.description == "step"][0]
        assert step.scheduled == task.scheduled


async def test_n_on_a_step_adds_a_step_beside_it():
    """
    A step has a home a sibling can share: its parent task

    The refusal is for gathered rows, which have no single project to add to.
    A step drawn under its task has one, so `n` there adds another step to the
    same task, on the same day, just as it would in the task's own project.
    """

    async with run_pilot() as pilot:
        app = await boot(pilot)

        await create_and_move_to_todo(pilot)
        await pilot.press("n")
        await commit_line(pilot, "task")
        await schedule(pilot, "today")

        await pilot.press("g", "t")
        await pilot.pause()

        today = visible_todos(app)

        await pilot.press("N")
        await commit_line(pilot, "first")
        await settle(pilot)

        await pilot.press("n")
        await commit_line(pilot, "second")
        await settle(pilot)

        assert descriptions(today) == ["task", "first", "second"]

        task = [todo for todo in Todo.all() if todo.description == "task"][0]
        second = [todo for todo in Todo.all() if todo.description == "second"][0]
        assert second.parent_todo is task
        assert second.scheduled == task.scheduled


async def test_a_new_step_goes_under_a_scheduled_step_too():
    """
    The row the key was pressed on is the row it goes under, context or not

    A step planned on its own is drawn under the task it belongs to, which is
    there for context alone. The cursor is on the step, so that is what takes
    the new one — and the task above stays what it was, a row the pane drew to
    say what the work is part of.
    """

    async with run_pilot() as pilot:
        app = await boot(pilot)

        await create_and_move_to_todo(pilot)
        await pilot.press("n")
        await commit_line(pilot, "task")
        await pilot.press("N")
        await commit_line(pilot, "step")
        await schedule(pilot, "today")

        await pilot.press("g", "t")
        await pilot.pause()

        today = visible_todos(app)
        assert descriptions(today) == ["step"]

        await pilot.press("N")
        await commit_line(pilot, "sub-step")
        await settle(pilot)

        assert descriptions(today) == ["step", "sub-step"]

        step = [todo for todo in Todo.all() if todo.description == "step"][0]
        sub = [todo for todo in Todo.all() if todo.description == "sub-step"][0]
        assert sub.parent_todo is step

        # The task above is still drawn for context and nothing else
        task = [todo for todo in Todo.all() if todo.description == "task"][0]
        assert context_ids(today) == [context_id(0, task)]


async def test_a_new_step_left_unnamed_is_dropped():
    """Escape throws away a step never given a name, as it does anywhere else"""

    async with run_pilot() as pilot:
        app = await boot(pilot)

        await create_and_move_to_todo(pilot)
        await pilot.press("n")
        await commit_line(pilot, "task")
        await schedule(pilot, "today")

        await pilot.press("g", "t")
        await pilot.pause()

        today = visible_todos(app)

        await pilot.press("N")
        await pilot.press("escape")
        await settle(pilot)

        assert descriptions(today) == ["task"]
        assert len(Todo.all()) == 1


async def test_the_refusal_points_at_the_key_that_does_work():
    """
    A task of its own has no project to land in here, and a step does

    Which is the whole of the difference, so the refusal says it: there is
    nowhere in a pane gathered out of the tree for a task beside another one,
    but the row under the cursor is somewhere a step can go.
    """

    async with run_pilot() as pilot:
        app = await boot(pilot)

        await create_and_move_to_todo(pilot)
        await pilot.press("n")
        await commit_line(pilot, "planned")
        await schedule(pilot, "today")

        await pilot.press("g", "t")
        await pilot.pause()

        await pilot.press("n")
        await pilot.pause()

        message = notification_message(app)
        assert message is not None
        assert "Tasks can't be added in [b]Today[/b]" in message
        assert "N" in message and "step" in message

        assert len(Todo.all()) == 1


async def test_the_log_and_the_bin_refuse_new_steps():
    """
    Nothing in either of them is being worked on, so nothing in them is broken
    down: a step written into a finished task would leave the log holding a row
    with work left in it, and one written into a binned task would be out of
    reach until the task came back.
    """

    async with run_pilot() as pilot:
        app = await boot(pilot)

        await create_and_move_to_todo(pilot)
        await pilot.press("n")
        await commit_line(pilot, "done deal")
        await pilot.press("c")
        await pilot.pause()

        await pilot.press("n")
        await commit_line(pilot, "dropped")
        await pilot.press("x", "x")
        await pilot.pause()

        for keys, title in ((("g", "c"), "Completed"), (("g", "b"), "Bin")):
            await pilot.press(*keys)
            await settle(pilot)

            await pilot.press("N")
            await pilot.pause()

            message = notification_message(app)
            assert message is not None, title
            assert f"Steps can't be added in [b]{title}[/b]" in message, title

            # And a task of its own is turned away with nothing to point at
            # instead, since there is nothing here that does work
            await pilot.press("n")
            await pilot.pause()

            message = notification_message(app)
            assert message == f"Tasks can't be added in [b]{title}[/b]", title

        assert len(Todo.all()) == 2


async def test_binning_from_today_removes_it_everywhere():
    async with run_pilot() as pilot:
        app = await boot(pilot)

        tree = await create_and_move_to_todo(pilot)
        await pilot.press("n")
        await commit_line(pilot, "planned")
        await schedule(pilot, "today")

        await pilot.press("g", "t")
        await pilot.pause()

        await pilot.press("x", "x")
        await pilot.pause()

        today_tree = visible_todos(app)
        assert tree_options(today_tree) == []
        assert tree_options(await reveal_project(pilot, tree.model)) == []

        todo = Todo.all()[0]
        assert todo.is_binned


async def test_binning_twice_warns_instead_of_stamping_again():
    async with run_pilot() as pilot:
        app = await boot(pilot)

        await new_project(pilot, "project")
        await new_todo(pilot, "doomed")

        await pilot.press("x", "x")
        await pilot.pause()

        await pilot.press("g", "b")
        await pilot.pause()

        await pilot.press("x", "x")
        await pilot.pause()

        message = notification_message(app)
        assert message is not None and "Already in the Bin" in message


async def test_restore_outside_the_bin_warns():
    async with run_pilot() as pilot:
        app = await boot(pilot)

        await new_project(pilot, "project")
        await new_todo(pilot, "still here")

        await pilot.press("u")
        await pilot.pause()

        message = notification_message(app)
        assert message is not None and "Bin" in message
        assert not Todo.all()[0].is_binned


async def test_restore_from_the_bin():
    async with run_pilot() as pilot:
        app = await boot(pilot)

        await create_and_move_to_todo(pilot)
        await pilot.press("n")
        await commit_line(pilot, "second thoughts")

        await pilot.press("x", "x")
        await pilot.pause()

        await pilot.press("g", "b")
        await pilot.pause()

        bin_tree = visible_todos(app)
        assert len(tree_options(bin_tree)) == 1

        with flashed() as flashes:
            await pilot.press("u")
            await settle(pilot)

        assert tree_options(bin_tree) == []

        todo = Todo.all()[0]
        assert not todo.is_binned
        assert todo.parent_project is not None
        assert todo.parent_project.description == "project"

        # And the app went with it: the project's own pane is in front, the
        # cursor is on the row, and the row was flashed
        tree = visible_todos(app)
        assert tree is not bin_tree
        assert tree.model is todo.parent_project
        assert tree.current_model is todo
        assert (tree.id, todo.uuid) in flashes


async def test_restoring_a_step_from_the_bin_brings_the_task_with_it():
    """
    The Bin puts a task back whole, and lands on the row the key was on

    Letting a step out on its own would drop it out of the app: the Bin has
    stopped holding it and the project is still hiding the task above it, so
    there would be nowhere left for the jump to go.
    """

    async with run_pilot() as pilot:
        app = await boot(pilot)

        tree = await create_and_move_to_todo(pilot)
        await pilot.press("n")
        await commit_line(pilot, "the task")
        await pilot.press("N")
        await commit_line(pilot, "the step")

        # From the task, so the whole family goes in
        await pilot.press("k")
        await pilot.pause()
        await pilot.press("x", "x")
        await pilot.pause()

        await pilot.press("g", "b")
        await pilot.pause()

        bin_tree = visible_todos(app)
        await settle(pilot)

        await pilot.press("l")
        await pilot.pause()
        assert bin_tree.current_model.description == "the step"

        with flashed() as flashes:
            await pilot.press("u")
            await settle(pilot)

        assert tree_options(bin_tree) == []
        assert not any(todo.is_binned for todo in Todo.all())

        step = [todo for todo in Todo.all() if todo.description == "the step"][0]

        # The task's own pane, on the row that was pressed rather than on the
        # task it came back inside
        assert visible_todos(app) is tree
        assert tree.current_model is step
        assert (tree.id, step.uuid) in flashes


async def test_restoring_a_finished_task_from_the_bin_goes_to_the_log():
    """
    Restoring does not untick: a task that was done goes back to the log

    The Bin and the completion log are two different things to have become,
    and coming out of one is not coming out of the other.
    """

    async with run_pilot() as pilot:
        app = await boot(pilot)

        await create_and_move_to_todo(pilot)
        await pilot.press("n")
        await commit_line(pilot, "done, then dropped")

        await pilot.press("c")
        await pilot.pause()
        await pilot.press("g", "c")
        await pilot.pause()

        completed = visible_todos(app)
        await settle(pilot)

        await pilot.press("x", "x")
        await pilot.pause()

        await pilot.press("g", "b")
        await pilot.pause()

        bin_tree = visible_todos(app)
        await settle(pilot)

        with flashed() as flashes:
            await pilot.press("u")
            await settle(pilot)

        todo = Todo.all()[0]
        assert not todo.is_binned
        assert todo.is_completed

        assert tree_options(bin_tree) == []
        assert visible_todos(app) is completed
        assert completed.current_model is todo
        assert (completed.id, todo.uuid) in flashes


async def test_empty_bin_via_chord():
    async with run_pilot() as pilot:
        app = await boot(pilot)

        await create_and_move_to_todo(pilot)
        for name in ("one", "two"):
            await pilot.press("n")
            await commit_line(pilot, name)
            await pilot.press("x", "x")
            await pilot.pause()

        # Only with the Bin open; the question counts what is about to go
        await pilot.press("g", "b")
        await pilot.pause()
        await pilot.press("Y", "Y")
        await pilot.pause()

        assert app.bar_switcher.current == "confirm_bar"
        assert "2 tasks" in app.bar_switcher.visible_content.message

        await pilot.press("y")
        await pilot.pause()

        assert Todo.all() == []


async def test_empty_chord_does_nothing_outside_bin_and_completed():
    async with run_pilot() as pilot:
        app = await boot(pilot)

        await create_and_move_to_todo(pilot)
        for name in ("binned", "done", "open"):
            await pilot.press("n")
            await commit_line(pilot, name)
        await pilot.press("x", "x")
        await pilot.pause()
        await pilot.press("k")
        await pilot.press("c")
        await pilot.pause()

        # Neither a project's pane nor another fixed one empties anything
        for jump in (None, ("g", "t"), ("g", "u")):
            if jump:
                await pilot.press(*jump)
                await pilot.pause()

            await pilot.press("Y", "Y")
            await pilot.pause()

            assert app.bar_switcher.current != "confirm_bar"
            message = notification_message(app)
            assert message is not None and "only empties" in message
            assert len(Todo.all()) == 3


async def test_empty_completed_via_chord():
    async with run_pilot() as pilot:
        app = await boot(pilot)

        await create_and_move_to_todo(pilot)
        for name in ("open", "done", "binned"):
            await pilot.press("n")
            await commit_line(pilot, name)

        # "binned" to the Bin, "done" ticked off; "open" stays open
        await pilot.press("x", "x")
        await pilot.pause()
        await pilot.press("c")
        await pilot.pause()

        await pilot.press("g", "c")
        await pilot.pause()
        await pilot.press("Y", "Y")
        await pilot.pause()

        assert app.bar_switcher.current == "confirm_bar"
        assert "1 task in Completed" in app.bar_switcher.visible_content.message

        await pilot.press("y")
        await pilot.pause()

        # Only the completed task went; the Bin and the open one are untouched
        left = sorted(t.description for t in Todo.all())
        assert left == ["binned", "open"]
        assert tree_options(visible_todos(app)) == []


async def test_deleting_from_the_bin_leaves_no_ghost_row():
    """
    A todo deleted for good in the Bin must be gone from its old project's
    pane as well — a pane that keeps a row for it hands the cursor a model
    that is no longer in the database, and the next edit crashes.
    """

    async with run_pilot() as pilot:
        app = await boot(pilot)

        tree = await create_and_move_to_todo(pilot)
        await pilot.press("n")
        await commit_line(pilot, "doomed")

        await pilot.press("x", "x")
        await pilot.pause()

        await pilot.press("g", "b")
        await pilot.pause()

        await pilot.press("y", "y")
        await pilot.pause()
        await pilot.press("y")
        await pilot.pause()

        assert Todo.all() == []

        # Back on the project the todo was filed under
        await pilot.press("j")
        await pilot.pause()
        app.project_tree.highlight_id(tree.model.uuid)
        await pilot.pause()
        await pilot.press("ö")
        await pilot.pause()

        pane = visible_todos(app)
        assert tree_options(pane) == []
        assert pane.highlighted is None


async def test_a_fixed_pane_gathers_its_blocks_once_per_redraw(monkeypatch):
    """
    Gathering is a query per block, so a redraw reads it once and lays every
    row out from that; nothing it draws goes back to the database for more
    """

    async with run_pilot() as pilot:
        app = await boot(pilot)
        await create_and_move_to_todo(pilot)

        await pilot.press("n")
        await commit_line(pilot, "planned")
        await schedule(pilot, "today")

        await pilot.press("g", "t")
        await pilot.pause()

        today = visible_todos(app)
        gathered = type(today.model).todo_groups
        reads = []

        def counted(project):
            reads.append(project)
            return gathered.fget(project)

        monkeypatch.setattr(type(today.model), "todo_groups", property(counted))

        today._refresh_and_restore_highlight()
        await pilot.pause()

        assert descriptions(today) == ["planned"]
        assert len(reads) == 1


class NextDay(date):
    """The date, as the clock reads it once midnight has passed"""

    @classmethod
    def today(cls):
        return date.today() + timedelta(days=1)


@pytest.fixture
def turn_the_day(monkeypatch):
    """Moves the clock past midnight for everything that gathers a pane"""

    def turn():
        for module in ("api.fixed_projects", "api.todo", "ui.screens.index"):
            # Through sys.modules: `todooit.api` re-exports a function under
            # the name of the fixed_projects module, shadowing it
            monkeypatch.setattr(sys.modules[f"todooit.{module}"], "date", NextDay)

    return turn


async def go_to(pilot, key: str):
    pilot.app.screen.post_message(GotoFixedProject(key))
    await settle(pilot)


async def tomorrows_task(pilot, name: str = "planned for tomorrow"):
    """A task planned for tomorrow, with the Today pane in front (without it)"""

    await create_and_move_to_todo(pilot)
    await pilot.press("n")
    await commit_line(pilot, name)
    await schedule(pilot, "tomorrow")
    await go_to(pilot, TODAY.key)


async def test_a_new_day_brings_its_tasks_onto_today(turn_the_day):
    async with run_pilot() as pilot:
        await boot(pilot)
        await create_and_move_to_todo(pilot)

        await pilot.press("n")
        await commit_line(pilot, "planned for today")
        await schedule(pilot, "today")
        await pilot.press("n")
        await commit_line(pilot, "planned for tomorrow")
        await schedule(pilot, "tomorrow")

        await go_to(pilot, TODAY.key)
        tree = visible_todos(pilot.app)
        assert descriptions(tree) == ["planned for today"]
        was_on = tree.node.id

        turn_the_day()
        pilot.app.screen.refresh_on_new_day()
        await pilot.pause()

        # Yesterday's task has slipped, so it leads; the cursor stays put
        assert descriptions(tree) == ["planned for today", "planned for tomorrow"]
        assert tree.node.id == was_on


async def test_a_new_day_relabels_a_pane_out_of_sight(turn_the_day):
    async with run_pilot() as pilot:
        await boot(pilot)
        await tomorrows_task(pilot)

        await go_to(pilot, UPCOMING.key)
        upcoming = visible_todos(pilot.app)
        assert [row.label for row in upcoming._rows.values() if row.label] == [
            "Tomorrow"
        ]

        await go_to(pilot, TODAY.key)

        turn_the_day()
        pilot.app.screen.refresh_on_new_day()
        await go_to(pilot, UPCOMING.key)

        assert [row.label for row in upcoming._rows.values() if row.label] == ["Today"]


async def test_the_same_day_redraws_nothing(monkeypatch):
    async with run_pilot() as pilot:
        await boot(pilot)

        redraws = []
        monkeypatch.setattr(
            pilot.app.screen, "refresh_panes", lambda changed: redraws.append(changed)
        )

        pilot.app.screen.refresh_on_new_day()

        assert redraws == []


async def test_a_new_day_waits_for_an_edit_to_finish(turn_the_day):
    async with run_pilot() as pilot:
        await boot(pilot)
        await tomorrows_task(pilot)
        await go_to(pilot, UPCOMING.key)

        tree = visible_todos(pilot.app)
        await pilot.press("s")
        await pilot.pause()
        assert tree.is_editing

        turn_the_day()
        pilot.app.screen.refresh_on_new_day()
        await pilot.pause()

        # The row being typed into is left alone, and the day isn't forgotten
        assert tree.is_editing
        assert [row.label for row in tree._rows.values() if row.label] == ["Tomorrow"]

        await pilot.press("escape")
        await pilot.pause()
        pilot.app.screen.refresh_on_new_day()
        await pilot.pause()

        assert [row.label for row in tree._rows.values() if row.label] == ["Today"]


async def test_a_new_day_waits_for_an_overlay_to_close(turn_the_day):
    async with run_pilot() as pilot:
        await boot(pilot)
        await tomorrows_task(pilot)

        main = pilot.app.screen
        tree = visible_todos(pilot.app)

        main.post_message(SpawnHelp())
        await settle(pilot)
        assert pilot.app.screen is not main

        turn_the_day()
        main.refresh_on_new_day()
        await pilot.pause()
        assert descriptions(tree) == []

        await pilot.app.pop_screen()
        await pilot.pause()
        main.refresh_on_new_day()
        await pilot.pause()

        assert descriptions(tree) == ["planned for tomorrow"]
