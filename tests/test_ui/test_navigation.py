"""
Moving around: pane focus, cursor keys, and the jumps to the fixed projects
"""

from todooit.api import BIN, COMPLETED, TODAY, UPCOMING
from tests.test_ui.ui_base import (
    boot,
    commit_line,
    create_and_move_to_todo,
    descriptions,
    highlighted_index,
    new_project,
    reveal_project,
    run_pilot,
    visible_todos,
)


async def test_focus_keys():
    async with run_pilot() as pilot:
        app = await boot(pilot)

        await pilot.press("j")
        assert app.focused is app.project_tree

        await pilot.press("ö")
        assert app.focused is visible_todos(app)

        await pilot.press("j")
        assert app.focused is app.project_tree


async def test_cursor_moves_in_the_todos_pane():
    async with run_pilot() as pilot:
        tree = await create_and_move_to_todo(pilot)

        for name in ("one", "two", "three"):
            await pilot.press("n")
            await commit_line(pilot, name)

        assert highlighted_index(tree) == 2

        await pilot.press("k")
        assert highlighted_index(tree) == 1

        await pilot.press("k")
        assert highlighted_index(tree) == 0

        # The header above the first row is furniture, not a place to stop
        await pilot.press("k")
        assert highlighted_index(tree) == 0

        await pilot.press("l")
        assert highlighted_index(tree) == 1

        await pilot.press("l", "l")
        assert highlighted_index(tree) == 2


async def test_top_and_bottom_of_the_todos_pane():
    async with run_pilot() as pilot:
        tree = await create_and_move_to_todo(pilot)

        for name in ("one", "two", "three"):
            await pilot.press("n")
            await commit_line(pilot, name)

        await pilot.press("g", "g")
        await pilot.pause()
        assert highlighted_index(tree) == 0

        await pilot.press("G")
        await pilot.pause()
        assert highlighted_index(tree) == 2


async def test_goto_today():
    async with run_pilot() as pilot:
        app = await boot(pilot)
        await new_project(pilot, "elsewhere")

        await pilot.press("g", "t")
        await pilot.pause()

        tree = visible_todos(app)
        assert tree.model is TODAY
        assert app.focused is tree
        assert app.project_tree.current_model is TODAY


async def test_goto_upcoming():
    async with run_pilot() as pilot:
        app = await boot(pilot)

        await pilot.press("g", "u")
        await pilot.pause()

        assert visible_todos(app).model is UPCOMING
        assert app.project_tree.current_model is UPCOMING


async def test_goto_completed():
    async with run_pilot() as pilot:
        app = await boot(pilot)

        await pilot.press("g", "c")
        await pilot.pause()

        assert visible_todos(app).model is COMPLETED
        assert app.project_tree.current_model is COMPLETED


async def test_goto_bin():
    async with run_pilot() as pilot:
        app = await boot(pilot)

        await pilot.press("g", "b")
        await pilot.pause()

        assert visible_todos(app).model is BIN
        assert app.project_tree.current_model is BIN


async def test_goto_lands_on_the_first_task():
    async with run_pilot() as pilot:
        app = await boot(pilot)
        await create_and_move_to_todo(pilot)

        await pilot.press("n")
        await commit_line(pilot, "planned")
        await pilot.press("s")
        await commit_line(pilot, "today")

        await pilot.press("g", "t")
        await pilot.pause()

        today_tree = visible_todos(app)
        assert today_tree.model is TODAY
        assert today_tree.current_model.description == "planned"


async def test_selecting_a_project_shows_its_pane():
    async with run_pilot() as pilot:
        app = await boot(pilot)
        ptree = app.project_tree

        first = await new_project(pilot, "first")
        second = await new_project(pilot, "second")

        ptree.highlight_id(first.uuid)
        await pilot.pause()
        assert visible_todos(app).model.uuid == first.uuid

        ptree.highlight_id(second.uuid)
        await pilot.pause()
        assert visible_todos(app).model.uuid == second.uuid


async def test_row_shading_toggle():
    async with run_pilot() as pilot:
        app = await boot(pilot)

        assert app.api.vars.row_shading is False

        await pilot.press("q")
        await pilot.pause()
        assert app.api.vars.row_shading is True

        await pilot.press("q")
        await pilot.pause()
        assert app.api.vars.row_shading is False


async def test_shaded_rows_alternate():
    async with run_pilot() as pilot:
        tree = await create_and_move_to_todo(pilot)

        for name in ("one", "two", "three", "four"):
            await pilot.press("n")
            await commit_line(pilot, name)

        await pilot.press("q")
        await pilot.pause()

        # Every other row, starting unshaded
        assert tree._shaded_rows == {1, 3}


async def test_a_pane_out_of_sight_catches_up_when_it_comes_forward():
    """
    A project pane is not redrawn while another one is in front of it

    The panes are never thrown away -- one per project visited stays mounted
    for the rest of the session -- so redrawing all of them on every change
    is work nobody can see, and it grows with how much of the tree has been
    opened. The redraw is owed until the pane comes forward, and this is the
    promise that it is paid then.
    """

    async with run_pilot() as pilot:
        app = await boot(pilot)

        first = await new_project(pilot, "first")
        await pilot.press("ö")
        await pilot.press("n")
        await commit_line(pilot, "todo in first")

        # A second project, whose pane takes the front
        second = await new_project(pilot, "second")
        await pilot.press("ö")
        assert visible_todos(app).model.description == "second"

        # Back onto the first and forward again, so its pane starts this
        # drawn and up to date rather than never having been in front
        await reveal_project(pilot, first)
        first_pane = visible_todos(app)
        await reveal_project(pilot, second)

        assert not first_pane.display
        assert not first_pane._needs_refresh

        # Renaming the todo in the pane behind marks it rather than redrawing
        todo = first.todos[0]
        todo.description = "renamed"
        todo.save()
        await pilot.pause()

        assert first_pane._needs_refresh

        # ... and it is drawn the moment it is looked at again
        revealed = await reveal_project(pilot, first)
        assert revealed is first_pane
        assert not first_pane._needs_refresh
        assert descriptions(revealed) == ["renamed"]


async def test_the_pane_in_front_is_still_redrawn_at_once():
    """The deferral is for the panes behind, and must not reach the front one"""

    async with run_pilot() as pilot:
        tree = await create_and_move_to_todo(pilot)

        await pilot.press("n")
        await commit_line(pilot, "before")

        todo = tree.model.todos[0]
        todo.description = "after"
        todo.save()
        await pilot.pause()

        assert not tree._needs_refresh
        assert descriptions(tree) == ["after"]


async def test_binning_from_a_pane_behind_reaches_the_bin():
    """
    A fixed pane goes back to the database when it comes forward

    What a fixed project shows is worked out from a query rather than kept,
    so a Bin that was out of sight while something was thrown away has to
    re-ask rather than draw what it last knew.
    """

    async with run_pilot() as pilot:
        app = await boot(pilot)

        tree = await create_and_move_to_todo(pilot)
        await pilot.press("n")
        await commit_line(pilot, "doomed")

        await pilot.press("x", "x")
        await pilot.pause()

        assert descriptions(tree) == []

        await pilot.press("g", "b")
        await pilot.pause()

        assert descriptions(visible_todos(app)) == ["doomed"]
