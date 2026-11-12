"""
Completed tasks stay in their project, hidden, and `.` shows them

Ticking a task off hides its row where it stands; `.` is one switch for the
session that draws every completed task back in its own place, and moves
nothing else. Restoring a completed task from the Bin puts it back in its
project, still completed, so still hidden.
"""

from tests.test_ui.ui_base import (
    boot,
    commit_line,
    create_and_move_to_todo,
    descriptions,
    notification_message,
    run_pilot,
    visible_todos,
)
from todooit.api import Project, Todo, move_project_to_bin


async def settle(pilot):
    """Waits out a jump to another pane, which can need building first"""

    for _ in range(5):
        await pilot.pause()


async def seed_rows(pilot, names=("a", "b", "c", "d")):
    for name in names:
        await pilot.press("n")
        await commit_line(pilot, name)

    return {todo.description: todo for todo in Todo.all()}


async def put_cursor_on(pilot, tree, name: str) -> None:
    for todo in Todo.all():
        if todo.description == name:
            tree.highlight_id(todo.uuid)

    await pilot.pause()
    assert tree.current_model.description == name


async def test_completed_tasks_start_hidden():
    async with run_pilot() as pilot:
        app = await boot(pilot)

        assert app.api.vars.show_completed is False


async def test_ticking_hides_the_row_and_drops_the_cursor_below():
    async with run_pilot() as pilot:
        tree = await create_and_move_to_todo(pilot)
        await seed_rows(pilot)

        await put_cursor_on(pilot, tree, "b")
        await pilot.press("c")
        await pilot.pause()

        assert descriptions(tree) == ["a", "c", "d"]
        assert tree.current_model.description == "c"

        # And undo brings it back, as for any change
        await pilot.press("u")
        await settle(pilot)

        assert descriptions(tree) == ["a", "b", "c", "d"]
        assert all(todo.is_pending for todo in Todo.all())


async def test_the_toggle_shows_completed_tasks_in_place_and_moves_nothing():
    async with run_pilot() as pilot:
        app = await boot(pilot)
        tree = await create_and_move_to_todo(pilot)
        todos = await seed_rows(pilot)

        todos["b"].toggle_complete()
        todos["d"].toggle_complete()
        tree.force_refresh()
        await pilot.pause()

        await put_cursor_on(pilot, tree, "c")
        assert descriptions(tree) == ["a", "c"]

        await pilot.press(".")
        await pilot.pause()

        # Shown among the open ones, where they were filed, the cursor kept
        assert app.api.vars.show_completed
        assert descriptions(tree) == ["a", "b", "c", "d"]
        assert tree.current_model.description == "c"

        await pilot.press(".")
        await pilot.pause()

        assert not app.api.vars.show_completed
        assert descriptions(tree) == ["a", "c"]
        assert tree.current_model.description == "c"


async def test_the_toggle_changes_the_view_not_the_data():
    """Undo walks past it to the last real change: making the project"""

    async with run_pilot() as pilot:
        app = await boot(pilot)
        await create_and_move_to_todo(pilot)

        await pilot.press(".")
        await pilot.pause()
        await pilot.press("u")
        await pilot.pause()

        assert app.api.vars.show_completed
        assert Project.all() == []


async def test_a_shown_completed_row_is_grayed_and_struck_through():
    async with run_pilot() as pilot:
        tree = await create_and_move_to_todo(pilot)
        todos = await seed_rows(pilot, ("open", "done"))

        todos["done"].toggle_complete()
        await pilot.press(".")
        await pilot.pause()

        drawn = tree.formatter.description.format_value("done", todos["done"])
        assert any(span.style and "strike" in str(span.style) for span in drawn.spans)


async def test_a_completed_step_hides_under_its_open_parent():
    async with run_pilot() as pilot:
        tree = await create_and_move_to_todo(pilot)

        await pilot.press("n")
        await commit_line(pilot, "plan trip")
        for name in ("book flights", "pack", "visa"):
            await pilot.press("N" if name == "book flights" else "n")
            await commit_line(pilot, name)

        todos = {todo.description: todo for todo in Todo.all()}
        await put_cursor_on(pilot, tree, "pack")
        await pilot.press("c")
        await pilot.pause()

        assert todos["plan trip"].is_pending
        assert descriptions(tree) == ["plan trip", "book flights", "visa"]

        # Folded, the count is of the open steps only
        await put_cursor_on(pilot, tree, "plan trip")
        await pilot.press("h")
        await pilot.pause()

        trip = todos["plan trip"]
        drawn = tree.formatter.description.format_value("plan trip", trip).plain
        assert drawn == "plan trip (2)"

        # Unfolded and shown, the step is back in its place
        await pilot.press("h", ".")
        await pilot.pause()
        assert descriptions(tree) == ["plan trip", "book flights", "pack", "visa"]


async def test_restoring_a_completed_task_rebuilds_its_project_and_keeps_it_hidden():
    async with run_pilot() as pilot:
        app = await boot(pilot)

        project = app.api.vars.projects_tree.model.add_project()
        project.description = "abandoned"
        project.save()
        todo = project.add_todo()
        todo.description = "finished work"
        todo.save()
        todo.toggle_complete()

        move_project_to_bin(project)
        app.api.vars.projects_tree.force_refresh()
        await pilot.pause()

        await pilot.press("g", "b")
        await settle(pilot)
        bin_tree = visible_todos(app)

        await pilot.press("R")
        await settle(pilot)

        rebuilt = todo.parent_project
        assert rebuilt is not None
        assert rebuilt.description == "revived - abandoned"
        assert [p.description for p in Project.all()] == ["revived - abandoned"]
        assert todo.is_completed and not todo.is_binned

        # Hidden where it went, so the cursor stays put and the bar says where
        assert visible_todos(app) is bin_tree
        assert notification_message(app) == (
            "Restored to [b]revived - abandoned[/b] (completed, hidden)"
        )

        # Shown, it is there in its rebuilt project
        app.api.vars.projects_tree.highlight_id(rebuilt.uuid)
        await pilot.pause()
        await pilot.press(".")
        await pilot.pause()
        assert descriptions(visible_todos(app)) == ["finished work"]
