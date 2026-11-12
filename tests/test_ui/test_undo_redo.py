"""
`u` and `ctrl+r` over the two panes: taking a key back, and pressing it again
"""

from unittest.mock import patch

import pytest
from textual.pilot import Pilot

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
from todooit.api import BIN, Project, Todo
from todooit.ui.tui import Todooit


async def undo(pilot: Pilot) -> None:
    await pilot.press("u")
    await pilot.pause()
    await pilot.pause()


async def redo(pilot: Pilot) -> None:
    await pilot.press("ctrl+r")
    await pilot.pause()
    await pilot.pause()


def descriptions(model) -> list:
    return sorted(row.description for row in model.all())


async def test_adding_a_task_is_one_undo():
    """
    The row is written before it is named, and both are taken back together

    Pressing `n` puts an empty todo in the database on the spot — the edit is
    typed into a row that already exists — so an undo that counted every
    commit would leave the name to be taken back before the row.
    """

    async with run_pilot() as pilot:
        tree = await create_and_move_to_todo(pilot)

        await pilot.press("n")
        await commit_line(pilot, "write it down")

        assert descriptions(Todo) == ["write it down"]

        await undo(pilot)

        assert Todo.all() == []
        assert len(tree_options(tree)) == 0


async def test_an_undone_task_comes_back_with_ctrl_r():
    async with run_pilot() as pilot:
        tree = await create_and_move_to_todo(pilot)

        await pilot.press("n")
        await commit_line(pilot, "write it down")

        await undo(pilot)
        assert Todo.all() == []

        await redo(pilot)

        assert descriptions(Todo) == ["write it down"]
        assert len(tree_options(tree)) == 1


async def test_an_edited_description_goes_back_to_what_it_was():
    async with run_pilot() as pilot:
        await create_and_move_to_todo(pilot)

        todo = await new_todo(pilot, "first name")

        await pilot.press("e", "c", "c")
        await commit_line(pilot, "second name")

        assert todo.description == "second name"

        await undo(pilot)

        assert todo.description == "first name"


async def test_a_priority_is_taken_back():
    async with run_pilot() as pilot:
        await create_and_move_to_todo(pilot)
        todo = await new_todo(pilot, "urgent")

        await pilot.press("p", "1")
        await pilot.pause()
        assert todo.priority == 1

        await undo(pilot)
        assert todo.priority == 0

        await redo(pilot)
        assert todo.priority == 1


async def test_a_task_thrown_in_the_bin_is_taken_back_out():
    async with run_pilot() as pilot:
        await create_and_move_to_todo(pilot)
        todo = await new_todo(pilot, "kept after all")

        await pilot.press("x", "x")
        await pilot.pause()
        assert todo.is_binned

        await undo(pilot)

        assert not todo.is_binned
        assert BIN.todos == []


async def test_a_task_deleted_for_good_is_put_back():
    """
    The one edit the app itself calls final is still one `u` away

    Nothing is written down about what the row held — the row itself is what
    was kept — so a delete comes back the same way every other change does.
    """

    async with run_pilot() as pilot:
        tree = await create_and_move_to_todo(pilot)
        await new_todo(pilot, "gone for good")

        # `yy` is the delete that asks first
        await pilot.press("y", "y")
        await pilot.pause()
        await pilot.press("y")
        await pilot.pause()

        assert Todo.all() == []

        await undo(pilot)

        assert descriptions(Todo) == ["gone for good"]
        assert len(tree_options(tree)) == 1


async def test_a_binned_project_comes_back_with_its_work_filed_under_it():
    """
    One key drops the row and files every task in the Bin; one key undoes both
    """

    async with run_pilot() as pilot:
        app = await boot(pilot)

        await new_project(pilot, "dropped")
        await pilot.press("ö", "n")
        await commit_line(pilot, "orphaned work")

        await pilot.press("j")
        await pilot.press("x", "x")
        await pilot.pause()

        assert Project.all() == []
        assert Todo.all()[0].is_binned

        await undo(pilot)

        project = Project.all()[0]
        todo = Todo.all()[0]

        assert project.description == "dropped"
        assert not todo.is_binned
        assert todo.parent_project_id == project.id
        assert len(tree_options(app.project_tree)) == 1


async def test_the_panes_redraw_over_what_a_step_left():
    """
    A row taken back out of the database is a row the panes let go of

    What a pane draws a row from outlives the row moving on, so a pane still
    holding one after an undo is a pane reading a table the row has left.
    """

    async with run_pilot() as pilot:
        app = await boot(pilot)

        await new_project(pilot, "project")
        await pilot.press("ö", "n")
        await commit_line(pilot, "work")

        tree = visible_todos(app)
        assert len(tree_options(tree)) == 1

        await undo(pilot)

        assert len(tree_options(visible_todos(app))) == 0

        await redo(pilot)

        assert len(tree_options(visible_todos(app))) == 1


async def test_undo_walks_back_one_key_at_a_time():
    async with run_pilot() as pilot:
        await create_and_move_to_todo(pilot)

        await new_todo(pilot, "first")
        await new_todo(pilot, "second")
        await new_todo(pilot, "third")

        await undo(pilot)
        assert descriptions(Todo) == ["first", "second"]

        await undo(pilot)
        assert descriptions(Todo) == ["first"]

        await undo(pilot)
        assert Todo.all() == []


async def test_the_way_forward_closes_once_something_else_is_typed():
    async with run_pilot() as pilot:
        await create_and_move_to_todo(pilot)

        await new_todo(pilot, "first")
        await undo(pilot)

        await new_todo(pilot, "second")
        await redo(pilot)

        assert descriptions(Todo) == ["second"]
        assert notification_message(pilot.app) == "Nothing left to redo"


async def test_a_pane_nobody_has_touched_has_nothing_to_take_back():
    async with run_pilot() as pilot:
        app = await boot(pilot)
        assert isinstance(app, Todooit)

        await undo(pilot)

        assert notification_message(app) == "Nothing left to undo"


async def test_a_step_says_how_much_it_moved():
    async with run_pilot() as pilot:
        app = await boot(pilot)
        await create_and_move_to_todo(pilot)
        await new_todo(pilot, "work")

        await undo(pilot)
        assert notification_message(app) == "Undone — 1 row dropped"

        await redo(pilot)
        assert notification_message(app) == "Redone — 1 row back"


async def test_a_note_written_over_the_panes_is_not_a_step_to_take_back():
    """
    Writing a note is not something `u` in the panes takes back

    The history does not keep notes -- see `history.NOTE` for why -- so a key
    that only wrote one leaves nothing behind to step onto, and `u`
    carries on to whatever was changed before it. The note window has an undo
    of its own, on the same key, which is where writing is actually done.
    """

    async with run_pilot() as pilot:
        await create_and_move_to_todo(pilot)
        todo = await new_todo(pilot, "has a note")

        await pilot.press(" ")
        await pilot.pause()
        # An empty note opens in INSERT
        await pilot.press(*list("call them"))

        # One escape out of INSERT, one to close the window
        await pilot.press("escape", "escape")
        await pilot.pause()
        await pilot.pause()

        assert todo.note.strip() == "call them"

        # The note stands. What the step takes back is the change before it --
        # here, the making of the todo the note was written on
        await undo(pilot)

        assert Todo.all() == []


async def test_the_undo_keys_are_left_alone_while_a_row_is_being_typed_into():
    """
    An edit in progress is the input's business, not the history's

    The row is already in the database by then, so a step taken mid-edit would
    take back a half-made task and leave the buffer typing into nothing. `u`
    is a letter there like any other.
    """

    async with run_pilot() as pilot:
        tree = await create_and_move_to_todo(pilot)

        await pilot.press("n")
        await pilot.press(*list("half typed "))

        await pilot.press("u", "ctrl+r")
        await pilot.pause()

        assert tree.is_editing
        assert len(Todo.all()) == 1

        await commit_line(pilot, "")
        assert descriptions(Todo) == ["half typed u"]


@pytest.mark.parametrize("key", ["ctrl+z", "ctrl+y"])
async def test_the_desktop_undo_keys_are_gone_from_the_panes(key):
    async with run_pilot() as pilot:
        await create_and_move_to_todo(pilot)
        await new_todo(pilot, "still here")

        with patch.object(pilot.app.api, "_step_history") as stepped:
            await pilot.press(key)
            await pilot.pause()
            await pilot.pause()

        stepped.assert_not_called()
        assert descriptions(Todo) == ["still here"]


async def test_u_in_the_bin_undoes_rather_than_restores():
    """`u` means one thing everywhere, the Bin included"""

    async with run_pilot() as pilot:
        app = await boot(pilot)
        await new_project(pilot, "project")
        await new_todo(pilot, "thrown away")

        await pilot.press("x", "x")
        await pilot.pause()
        await pilot.press("g", "b")
        await pilot.pause()

        await undo(pilot)

        # The undo took back the throwing away: the row is out of the Bin and
        # home again, not rebuilt into a "revived" project as a restore would
        todo = Todo.all()[0]
        assert not todo.is_binned
        assert [p.description for p in Project.all()] == ["project"]
        assert tree_options(visible_todos(app)) == []


async def test_R_restores_from_the_bin_and_u_takes_the_restore_back():
    async with run_pilot() as pilot:
        await boot(pilot)
        await new_project(pilot, "project")
        await new_todo(pilot, "thrown away")

        await pilot.press("x", "x")
        await pilot.pause()
        await pilot.press("g", "b")
        await pilot.pause()

        await pilot.press("R")
        await pilot.pause()
        await pilot.pause()
        assert not Todo.all()[0].is_binned

        await undo(pilot)
        assert Todo.all()[0].is_binned

        await redo(pilot)
        assert not Todo.all()[0].is_binned
