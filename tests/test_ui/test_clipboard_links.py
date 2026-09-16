"""
The system clipboard on the tasks pane, and the `o` that opens a row's link
"""

from unittest.mock import patch

from todooit.ui.screens.note import NoteScreen

from tests.test_ui.ui_base import (
    commit_line,
    create_and_move_to_todo,
    highlighted_index,
    notification_message,
    run_pilot,
    set_clipboard,
    tree_options,
)


async def test_copy_todo_description():
    async with run_pilot() as pilot:
        app = pilot.app
        await create_and_move_to_todo(pilot)

        await pilot.press("n")
        await commit_line(pilot, "copy me")

        await pilot.press("ctrl+c")
        await pilot.pause()

        assert app.clipboard == "copy me"


async def test_paste_todo_as_sibling():
    async with run_pilot() as pilot:
        tree = await create_and_move_to_todo(pilot)

        set_clipboard("  pasted \n  task  ")
        await pilot.press("ctrl+v")
        await pilot.pause()

        # One line, whatever the clipboard was
        assert len(tree_options(tree)) == 1
        assert tree.current_model.description == "pasted task"

        await pilot.press("ctrl+v")
        await pilot.pause()

        assert len(tree_options(tree)) == 2
        assert highlighted_index(tree) == 1


async def test_paste_with_an_empty_clipboard_warns():
    async with run_pilot() as pilot:
        app = pilot.app
        tree = await create_and_move_to_todo(pilot)

        set_clipboard("   ")
        await pilot.press("ctrl+v")
        await pilot.pause()

        assert tree_options(tree) == []
        message = notification_message(app)
        assert message is not None and "empty" in message.lower()


async def test_paste_into_an_edit_pastes_text():
    """Inside an edit, ctrl+v is a text paste, not a new row"""

    async with run_pilot() as pilot:
        tree = await create_and_move_to_todo(pilot)

        set_clipboard("pasted words")

        await pilot.press("n")
        await pilot.press(*list("start "))
        await pilot.press("ctrl+v")
        await pilot.press("enter")
        await pilot.pause()

        assert len(tree_options(tree)) == 1
        assert tree.current_model.description == "start pasted words"


async def test_open_link_on_a_row():
    async with run_pilot() as pilot:
        app = pilot.app
        opened = []

        with patch(
            "todooit.ui.api.dooit_api.open_url",
            lambda url: opened.append(url) or True,
        ):
            await create_and_move_to_todo(pilot)

            await pilot.press("n")
            await commit_line(pilot, "read https://example.com/docs today")

            await pilot.press("o")
            await pilot.pause()

            assert opened == ["https://example.com/docs"]

            message = notification_message(app)
            assert message is not None and "Opening" in message


async def test_open_link_without_one_warns():
    async with run_pilot() as pilot:
        app = pilot.app
        opened = []

        with patch(
            "todooit.ui.api.dooit_api.open_url",
            lambda url: opened.append(url) or True,
        ):
            await create_and_move_to_todo(pilot)

            await pilot.press("n")
            await commit_line(pilot, "nothing to open")

            await pilot.press("o")
            await pilot.pause()

            assert opened == []
            message = notification_message(app)
            assert message is not None and "No link" in message


async def test_open_link_with_no_browser_reports_it():
    async with run_pilot() as pilot:
        app = pilot.app

        with patch("todooit.ui.api.dooit_api.open_url", lambda url: False):
            await create_and_move_to_todo(pilot)

            await pilot.press("n")
            await commit_line(pilot, "see www.example.com")

            await pilot.press("o")
            await pilot.pause()

            message = notification_message(app)
            assert message is not None and "browser" in message


async def test_copy_todo_note():
    """ctrl+n takes the whole note without the note window coming up"""

    async with run_pilot() as pilot:
        app = pilot.app
        tree = await create_and_move_to_todo(pilot)

        await pilot.press("n")
        await commit_line(pilot, "task with a note")

        todo = tree.current_model
        todo.note = "first line\nsecond line"
        todo.save()

        await pilot.press("ctrl+n")
        await pilot.pause()

        assert app.clipboard == "first line\nsecond line"
        assert not isinstance(app.screen, NoteScreen)

        message = notification_message(app)
        assert message is not None and "copied" in message.lower()


async def test_copy_note_without_one_warns():
    async with run_pilot() as pilot:
        app = pilot.app

        await create_and_move_to_todo(pilot)

        await pilot.press("n")
        await commit_line(pilot, "no note here")

        await pilot.press("ctrl+n")
        await pilot.pause()

        assert app.clipboard == ""
        message = notification_message(app)
        assert message is not None and "no note" in message.lower()


async def test_copy_note_on_the_projects_pane_does_nothing():
    """A project has no note, so the key is not its key"""

    async with run_pilot() as pilot:
        app = pilot.app
        tree = await create_and_move_to_todo(pilot)

        await pilot.press("n")
        await commit_line(pilot, "task with a note")

        todo = tree.current_model
        todo.note = "not this"
        todo.save()

        await pilot.press("j")
        await pilot.pause()

        await pilot.press("ctrl+n")
        await pilot.pause()

        assert app.clipboard == ""
