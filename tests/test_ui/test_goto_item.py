"""
`gi`: the task under the cursor, in the project it is really filed under
"""

from tests.test_ui.test_fixed_panes import flashed, schedule, settle
from tests.test_ui.ui_base import (
    boot,
    commit_line,
    new_project,
    new_todo,
    notification_message,
    run_pilot,
    visible_todos,
)
from todooit.api import Project, Todo


async def test_goto_item_from_today_opens_the_project():
    """The arrival the finder makes, asked for from the row itself"""

    async with run_pilot() as pilot:
        app = await boot(pilot)

        await new_project(pilot, "home")
        todo = await new_todo(pilot, "water plants")
        await schedule(pilot, "today")

        home = visible_todos(app)
        project = home.model

        await pilot.press("g", "t")
        await pilot.pause()

        today = visible_todos(app)
        assert today is not home
        assert today.current_model is todo

        with flashed() as flashes:
            await pilot.press("g", "i")
            await settle(pilot)

        # The project's own pane in front and focused, the cursor on the row,
        # and the row flashed so it is the one that was asked for
        assert visible_todos(app) is home
        assert app.focused is home
        assert home.current_model is todo
        assert (home.id, todo.uuid) in flashes

        # And the projects pane came along, so the two sides agree
        assert app.project_tree.current_model is project


async def test_goto_item_goes_to_a_step_gathered_on_its_own():
    """
    A step the day gathered is found as the step, not as the task above it

    Today draws such a row under the task it belongs to for context; `gi` is
    pressed on the step, so the step is where the cursor lands over there.
    """

    async with run_pilot() as pilot:
        app = await boot(pilot)

        await new_project(pilot, "home")
        await new_todo(pilot, "tidy the shed")
        await pilot.press("N")
        await commit_line(pilot, "sort the tools")
        await schedule(pilot, "today")

        home = visible_todos(app)
        step = home.current_model
        assert isinstance(step, Todo)
        assert step.parent_todo is not None

        await pilot.press("g", "t")
        await pilot.pause()

        today = visible_todos(app)
        assert today.current_model is step

        await pilot.press("g", "i")
        await settle(pilot)

        assert visible_todos(app) is home
        assert home.current_model is step


async def test_goto_item_from_upcoming_opens_the_project():
    async with run_pilot() as pilot:
        app = await boot(pilot)

        await new_project(pilot, "work")
        todo = await new_todo(pilot, "write report")
        await schedule(pilot, "tomorrow")

        work = visible_todos(app)

        await pilot.press("g", "u")
        await pilot.pause()

        upcoming = visible_todos(app)
        assert upcoming.current_model is todo

        await pilot.press("g", "i")
        await settle(pilot)

        assert visible_todos(app) is work
        assert app.focused is work
        assert work.current_model is todo


async def test_goto_item_opens_the_sub_project_a_row_belongs_to():
    """
    A project pane draws the work of everything nested under it too

    Those rows live a pane away just as the gathered ones do, so the key goes
    there: the block heading says which project, and this stands on the row.
    """

    async with run_pilot() as pilot:
        app = await boot(pilot)

        await new_project(pilot, "home")

        await pilot.press("N")
        await commit_line(pilot, "kitchen")

        kitchen = app.project_tree.current_model
        assert isinstance(kitchen, Project)

        todo = await new_todo(pilot, "fix the sink")
        kitchen_pane = visible_todos(app)

        # Up to the project the sub project sits in, whose pane draws the row
        # under a heading of its own
        await pilot.press("j", "k", "ö")
        await pilot.pause()

        home_pane = visible_todos(app)
        assert home_pane is not kitchen_pane
        assert home_pane.current_model is todo

        await pilot.press("g", "i")
        await settle(pilot)

        assert visible_todos(app) is kitchen_pane
        assert kitchen_pane.current_model is todo
        assert app.project_tree.current_model is kitchen


async def test_goto_item_on_a_row_at_home_says_so():
    """Pressed where the row already lives, the key says so and stays put"""

    async with run_pilot() as pilot:
        app = await boot(pilot)

        await new_project(pilot, "home")
        todo = await new_todo(pilot, "water plants")

        home = visible_todos(app)

        await pilot.press("g", "i")
        await settle(pilot)

        assert notification_message(app) == "This is the project it lives in"
        assert visible_todos(app) is home
        assert home.current_model is todo


async def test_the_log_and_the_bin_turn_goto_item_away():
    """
    Neither of them is somewhere a row was gathered from: it is where it is

    A finished task has left the pane of the project it was filed under and a
    thrown away one has too, so there is no row over there to walk to — and
    the key that gives it one back already takes the cursor with it.
    """

    async with run_pilot() as pilot:
        app = await boot(pilot)

        await new_project(pilot, "home")

        await new_todo(pilot, "done deal")
        await pilot.press("c")
        await pilot.pause()

        await pilot.press("n")
        await commit_line(pilot, "dropped")
        await pilot.press("x", "x")
        await pilot.pause()

        refusals = (
            (("g", "c"), "Completed", "c"),
            (("g", "b"), "Bin", "u"),
        )

        for keys, title, instead in refusals:
            await pilot.press(*keys)
            await settle(pilot)

            pane = visible_todos(app)

            await pilot.press("g", "i")
            await settle(pilot)

            message = notification_message(app)
            assert message is not None, title
            assert f"Tasks can't be gone to in [b]{title}[/b]" in message, title
            assert f"[b]{instead}[/b]" in message, title

            # And nothing moved: the pane is still the one that was in front
            assert visible_todos(app) is pane, title


async def test_goto_item_is_the_tasks_pane_alone():
    """
    Over the projects there is nothing to go to: the row is its own pane

    The binding is scoped, so the chord simply finds nothing there rather than
    doing something to the project under the cursor.
    """

    async with run_pilot() as pilot:
        app = await boot(pilot)

        await new_project(pilot, "home")
        await new_todo(pilot, "water plants")

        home = visible_todos(app)

        await pilot.press("j")
        await pilot.pause()

        await pilot.press("g", "i")
        await settle(pilot)

        assert app.focused is app.project_tree
        assert visible_todos(app) is home
