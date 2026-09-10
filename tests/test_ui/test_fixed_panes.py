"""
The panes of the fixed projects: what they draw, and what they turn away
"""


from rich.style import Style as RichStyle
from textual.style import Style

from todooit.api import Todo
from todooit.ui.widgets.renderers.base_renderer import GUIDE_LAST_BRANCH
from todooit.ui.widgets.trees.fixed_todos_tree import RESCHEDULE_MARK
from tests.test_ui.ui_base import (
    boot,
    commit_line,
    create_and_move_to_todo,
    new_project,
    new_todo,
    notification_message,
    run_pilot,
    tree_options,
    visible_todos,
)


async def schedule(pilot, when: str):
    """Schedules the highlighted todo by typing into the `s` edit"""

    await pilot.press("s")
    await commit_line(pilot, when)


def descriptions(tree):
    """What the pane's stored rows say, top to bottom"""

    return [tree._renderers[o.id].model.description for o in tree_options(tree)]


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
        if (o.id or "").startswith("dooit-todo-context-")
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
            if _id and _id.startswith("dooit-todo-group")
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
        assert context_ids(today) == [today._context_id(0, task)]

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

        guide = today._renderers[planned.uuid].tree_guide.plain
        assert guide == GUIDE_LAST_BRANCH


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
            upcoming._context_id(0, task),
            upcoming._context_id(1, task),
        ]


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
        assert today.row_mark(missed).plain == RESCHEDULE_MARK

        # Nothing to say about a row that is where it was planned to be
        assert today.row_mark(planned).plain == ""

        # And nothing added after the description either
        assert today.row_note(missed).plain == ""


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

        assert drawn.index(RESCHEDULE_MARK) < drawn.index("missed")

        marks = [color for text, color in segments if RESCHEDULE_MARK.strip() in text]
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
        assert upcoming.row_mark(missed).plain == RESCHEDULE_MARK
        assert upcoming.row_mark(soon).plain == ""

        # The project a row came out of is still the only thing after it
        assert "project" in upcoming.row_note(missed).plain


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


async def test_completed_holds_an_unticked_row():
    """Unticking in the log must not drop the row out from under the edit"""

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
        await pilot.press("c")  # untick it right there
        await pilot.pause()

        todo = Todo.all()[0]
        assert todo.is_pending

        # Still on screen in the log, held while it is being seen to
        assert len(tree_options(completed)) == 1

        # And back in its own project's pane at the same time
        assert len(tree_options(tree)) == 1


async def test_fixed_panes_refuse_reordering_and_adding():
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
            (("N",), "added"),
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
        assert tree_options(tree) == []

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

        await pilot.press("u")
        await pilot.pause()

        assert tree_options(bin_tree) == []

        todo = Todo.all()[0]
        assert not todo.is_binned
        assert todo.parent_project is not None
        assert todo.parent_project.description == "project"


async def test_empty_bin_via_chord():
    async with run_pilot() as pilot:
        app = await boot(pilot)

        await create_and_move_to_todo(pilot)
        for name in ("one", "two"):
            await pilot.press("n")
            await commit_line(pilot, name)
            await pilot.press("x", "x")
            await pilot.pause()

        # From anywhere at all; the question counts what is about to go
        await pilot.press("Y", "Y")
        await pilot.pause()

        assert app.bar_switcher.current == "confirm_bar"
        assert "2 tasks" in app.bar_switcher.visible_content.message

        await pilot.press("y")
        await pilot.pause()

        assert Todo.all() == []


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
