"""
The tasks pane of a stored project: adding, editing, and every column
"""

from datetime import date, datetime, timedelta

import pytest
from pytest import raises

from tests.test_ui.ui_base import (
    commit_line,
    create_and_move_to_todo,
    highlighted_index,
    new_todo,
    notification_message,
    run_pilot,
    tree_options,
)
from todooit.api import Cadence, Todo
from todooit.api.exceptions import NoNodeError
from todooit.ui.api.widgets import TodoWidget
from todooit.ui.tui import Todooit
from todooit.ui.widgets.renderers.base_renderer import BaseRenderer
from todooit.ui.widgets.trees.todos_tree import DATE_COLUMN_ICON


def custom_formatter(value, todo):
    return "??"


async def test_todo_tree_focus():
    async with run_pilot() as pilot:
        app = pilot.app
        assert isinstance(app, Todooit)
        await create_and_move_to_todo(pilot)


async def test_no_node_error():
    async with run_pilot() as pilot:
        tree = await create_and_move_to_todo(pilot)

        with raises(NoNodeError):
            _ = tree.current


async def test_add_todo_via_keys():
    async with run_pilot() as pilot:
        tree = await create_and_move_to_todo(pilot)

        await pilot.press("n")
        await commit_line(pilot, "first")

        await pilot.press("n")
        await commit_line(pilot, "second")

        assert [t.description for t in Todo.all()] == ["first", "second"]
        assert len(tree_options(tree)) == 2
        assert highlighted_index(tree) == 1


@pytest.mark.parametrize("key", ["n", "i", "a"])
async def test_every_add_key_adds_a_sibling(key):
    async with run_pilot() as pilot:
        tree = await create_and_move_to_todo(pilot)
        first = await new_todo(pilot, "first")
        await new_todo(pilot, "last")
        await pilot.press("k")

        # The name holds the key itself: past the first press it is only text
        await pilot.press(key)
        await commit_line(pilot, f"nia {key}")

        added = tree.current_model
        assert isinstance(added, Todo)
        assert added.description == f"nia {key}"
        assert added.parent_project == first.parent_project
        assert [todo.description for todo in added.siblings] == [
            "first",
            f"nia {key}",
            "last",
        ]


async def test_a_new_todo_left_without_a_name_is_dropped():
    async with run_pilot() as pilot:
        tree = await create_and_move_to_todo(pilot)

        # Out of INSERT, then out of the edit with nothing in it
        await pilot.press("n")
        await pilot.press("escape", "escape")
        await pilot.pause()

        assert Todo.all() == []
        assert tree_options(tree) == []


async def test_blank_todo_is_dropped():
    async with run_pilot() as pilot:
        tree = await create_and_move_to_todo(pilot)

        await pilot.press("n")
        await commit_line(pilot, "   ")

        assert Todo.all() == []
        assert tree_options(tree) == []


async def test_blanking_a_todo_with_steps_asks_first():
    """Dropping it would take everything under it along"""

    async with run_pilot() as pilot:
        app = pilot.app
        await create_and_move_to_todo(pilot)

        await pilot.press("n")
        await commit_line(pilot, "parent")
        await pilot.press("N")
        await commit_line(pilot, "step")

        # Blank the parent's name and commit
        await pilot.press("k")  # up to the parent
        await pilot.press("e", "c", "c")
        await pilot.press("enter")
        await pilot.pause()

        assert app.bar_switcher.current == "confirm_bar"

        await pilot.press("n")
        await pilot.pause()

        # Cancelled: both rows survive, the parent just has no name yet
        assert len(Todo.all()) == 2


async def test_add_child_and_expansion():
    async with run_pilot() as pilot:
        tree = await create_and_move_to_todo(pilot)

        await pilot.press("n")
        await commit_line(pilot, "task")
        await pilot.press("N")
        await commit_line(pilot, "step")

        step = next(t for t in Todo.all() if t.description == "step")
        assert step.parent_todo is not None
        assert step.parent_todo.description == "task"

        # The parent was expanded on the way in; the cursor is on the step
        assert len(tree_options(tree)) == 2
        assert tree.current_model.uuid == step.uuid

        # Fold the parent away and open it again
        await pilot.press("k", "h")
        await pilot.pause()
        assert len(tree_options(tree)) == 1

        await pilot.press("h")
        await pilot.pause()
        assert len(tree_options(tree)) == 2


async def test_child_count_shows_only_while_collapsed():
    """
    An open todo has its steps on the rows below it, so the count trailing its
    description is only drawn once it is folded shut
    """

    async with run_pilot() as pilot:
        tree = await create_and_move_to_todo(pilot)

        await pilot.press("n")
        await commit_line(pilot, "task")
        await pilot.press("N")
        await commit_line(pilot, "step")

        task = next(t for t in Todo.all() if t.description == "task")

        def drawn() -> str:
            return tree.formatter.description.format_value("task", task).plain

        assert drawn() == "task"

        await pilot.press("k", "h")
        await pilot.pause()
        assert drawn() == "task (1)"

        await pilot.press("h")
        await pilot.pause()
        assert drawn() == "task"


async def test_edit_description():
    async with run_pilot() as pilot:
        await create_and_move_to_todo(pilot)

        await pilot.press("n")
        await commit_line(pilot, "old")

        await pilot.press("e", "c", "c")
        await commit_line(pilot, "new")

        assert Todo.all()[0].description == "new"


async def test_todo_formatter():
    def get_formatted(renderer: BaseRenderer, attr: str):
        component = renderer._get_component(attr)
        formatter = renderer.tree.formatter
        return (
            getattr(formatter, attr)
            .format_value(component.model_value, component.model)
            .markup
        )

    async with run_pilot() as pilot:
        app = pilot.app
        assert isinstance(app, Todooit)

        tree = await create_and_move_to_todo(pilot)

        await pilot.press("n")
        await commit_line(pilot, "nixos")

        renderer = tree.current
        assert get_formatted(renderer, "description") == "nixos"

        app.api.formatter.todos.description.add(custom_formatter)
        assert get_formatted(renderer, "description") == "??"


async def test_todo_tree_layout():
    async with run_pilot() as pilot:
        app = pilot.app
        assert isinstance(app, Todooit)

        tree = await create_and_move_to_todo(pilot)

        await pilot.press("n")
        await commit_line(pilot, "nixos")

        table = tree.render_row(tree._rows[tree.current.id])
        assert table.columns[0].header == "status"

        app.api.layouts.todo_layout = [TodoWidget.description]
        table = tree.render_row(tree._rows[tree.current.id])
        assert table.columns[0].header == "description"


async def test_status_and_note_columns_go_untitled():
    """The checkbox and the note icon need no header, so neither column is widened by one"""

    async with run_pilot() as pilot:
        tree = await create_and_move_to_todo(pilot)

        await pilot.press("n")
        await commit_line(pilot, "nixos")

        assert tree.column_title("status") == ""
        assert tree.column_title("note") == ""
        assert tree.column_title("description") == "Description"

        tree.get_column_width.cache_clear()
        assert tree.get_column_width("status") < len("Status")
        assert tree.get_column_width("note") < len("Note")


async def test_date_icon_sits_in_the_header_and_rows_drop_the_year():
    """The calendar is drawn once per date column, and a row's date leaves the year off"""

    async with run_pilot() as pilot:
        tree = await create_and_move_to_todo(pilot)

        await pilot.press("n")
        await commit_line(pilot, "nixos")

        todo = tree.current_model
        assert isinstance(todo, Todo)
        when = datetime(date.today().year + 1, 3, 7)
        todo.due = when
        todo.scheduled = when
        todo.save()

        assert tree.column_title("due") == f"{DATE_COLUMN_ICON} Due"
        assert tree.column_title("scheduled") == f"{DATE_COLUMN_ICON} Scheduled"

        for column in ("due", "scheduled"):
            drawn = getattr(tree.formatter, column).format_value(when, todo).plain
            assert drawn.endswith("07.03.")
            assert DATE_COLUMN_ICON not in drawn

        # Stored in full all the same
        assert todo.due.year == when.year


async def test_incorrect_edit():
    async with run_pilot() as pilot:
        tree = await create_and_move_to_todo(pilot)

        await pilot.press("n")
        await commit_line(pilot, "nixos")

        assert not tree.current.start_edit("incorrect")


async def test_remove_todo():
    async with run_pilot() as pilot:
        tree = await create_and_move_to_todo(pilot)

        await pilot.press("n")
        await commit_line(pilot, "nixos")

        # `yy` is the delete that asks first
        await pilot.press("y", "y")
        await pilot.pause()

        assert len(tree_options(tree)) == 1
        assert highlighted_index(tree) == 0
        assert tree.current_model.description == "nixos"

        await pilot.press("y")
        await pilot.pause()

        assert len(tree_options(tree)) == 0
        assert tree.highlighted is None
        assert Todo.all() == []


async def test_due():
    async with run_pilot() as pilot:
        tree = await create_and_move_to_todo(pilot)

        await pilot.press("n")
        await commit_line(pilot, "nixos")

        await pilot.press("d")
        await commit_line(pilot, "2022-01-01")

        todo = tree.current_model
        assert isinstance(todo, Todo)
        assert todo.due == datetime(2022, 1, 1)


async def test_scheduled():
    async with run_pilot() as pilot:
        tree = await create_and_move_to_todo(pilot)

        await pilot.press("n")
        await commit_line(pilot, "nixos")

        await pilot.press("s")
        await commit_line(pilot, "2033-05-05")

        todo = tree.current_model
        assert isinstance(todo, Todo)
        assert todo.scheduled == datetime(2033, 5, 5)
        assert todo.due is None


async def test_due_natural_language():
    async with run_pilot() as pilot:
        tree = await create_and_move_to_todo(pilot)

        await pilot.press("n")
        await commit_line(pilot, "nixos")

        await pilot.press("d")
        await commit_line(pilot, "tom 16:00")

        todo = tree.current_model
        assert isinstance(todo, Todo)

        expected = datetime.now().replace(
            hour=16, minute=0, second=0, microsecond=0
        ) + timedelta(days=1)
        assert todo.due == expected


async def test_due_preview_while_editing():
    async with run_pilot() as pilot:
        tree = await create_and_move_to_todo(pilot)

        await pilot.press("n")
        await commit_line(pilot, "nixos")

        await pilot.press("d")
        await pilot.press(*list("tom"))

        component = tree.current._get_component("due")
        preview = component.render_editing(tree.current.theme).plain

        tomorrow = datetime.now() + timedelta(days=1)
        assert preview.endswith(f"→ {tomorrow.strftime('%d.%m.%Y')}")

        # and an expression that means nothing says so, rather than guessing
        await pilot.press("ctrl+l")
        await pilot.press(*list("asdfgh"))
        assert component.render_editing(tree.current.theme).plain.endswith("→ ?")

        await pilot.press("escape")


async def test_due_invalid_keeps_previous_value():
    async with run_pilot() as pilot:
        app = pilot.app
        tree = await create_and_move_to_todo(pilot)

        await pilot.press("n")
        await commit_line(pilot, "nixos")

        await pilot.press("d")
        await commit_line(pilot, "2022-01-01")

        todo = tree.current_model
        assert isinstance(todo, Todo)
        assert todo.due == datetime(2022, 1, 1)

        # Committing garbage: the date that was there survives, and the bar
        # says why instead of the edit being silently dropped
        await pilot.press("d", "ctrl+l")
        await commit_line(pilot, "asdfgh")

        assert todo.due == datetime(2022, 1, 1)
        assert not tree.is_editing

        message = notification_message(app)
        assert message is not None and "asdfgh" in message


async def test_due_refused_on_recurring_todo():
    """What repeats is never owed by a date, and typing one is turned away"""

    async with run_pilot() as pilot:
        app = pilot.app
        tree = await create_and_move_to_todo(pilot)

        await pilot.press("n")
        await commit_line(pilot, "weekly review")

        await pilot.press("r")
        await commit_line(pilot, "1w")

        todo = tree.current_model
        assert isinstance(todo, Todo)
        assert todo.recurrence == Cadence(1, "weeks")

        await pilot.press("d")
        await commit_line(pilot, "tomorrow")

        assert todo.due is None
        message = notification_message(app)
        assert message is not None and "recurring" in message


async def test_priority_keybinds():
    async with run_pilot() as pilot:
        tree = await create_and_move_to_todo(pilot)

        await pilot.press("n")
        await commit_line(pilot, "nixos")

        todo = tree.current_model
        assert isinstance(todo, Todo)
        assert todo.priority == 0

        await pilot.press("p", "1")
        await pilot.pause()
        assert todo.priority == 1

        await pilot.press("p", "3")
        await pilot.pause()
        assert todo.priority == 3

        await pilot.press("p", "0")
        await pilot.pause()
        assert todo.priority == 0


async def test_status_change():
    async with run_pilot() as pilot:
        tree = await create_and_move_to_todo(pilot)

        await pilot.press("n")
        await commit_line(pilot, "nixos")

        await pilot.press("d")
        await commit_line(pilot, "2022-01-01")

        todo = tree.current_model
        assert isinstance(todo, Todo)
        assert todo.status == "overdue"

        todo.toggle_complete()
        assert todo.status == "completed"


async def test_recurrence_change():
    async with run_pilot() as pilot:
        tree = await create_and_move_to_todo(pilot)

        await pilot.press("n")
        await commit_line(pilot, "nixos")

        todo = tree.current_model
        assert isinstance(todo, Todo)
        assert todo.recurrence is None

        await pilot.press("r")
        await commit_line(pilot, "1d")

        assert todo.recurrence == Cadence(1, "days")


async def test_completing_a_recurring_todo_advances_it():
    async with run_pilot() as pilot:
        tree = await create_and_move_to_todo(pilot)

        await pilot.press("n")
        await commit_line(pilot, "daily standup")

        await pilot.press("s")
        await commit_line(pilot, "today")
        await pilot.press("r")
        await commit_line(pilot, "1d")

        todo = tree.current_model
        assert isinstance(todo, Todo)

        await pilot.press("c")
        await pilot.pause()

        # Never finished, only done for now: pending again, one day on, and
        # still the only row of its pane
        assert todo.is_pending
        assert todo.scheduled is not None
        assert todo.scheduled.date() == date.today() + timedelta(days=1)
        assert len(tree_options(tree)) == 1
