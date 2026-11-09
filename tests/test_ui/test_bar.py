"""
The bar under the panes: the status line, and the bars that take it over

Notifications, the y/N that guards a delete, and the field editor a fixed
pane borrows when a hidden column is edited. The sort chords are tested in
test_sort.py.
"""

from typing import Optional

from tests.test_ui.ui_base import (
    boot,
    commit_line,
    create_and_move_to_todo,
    new_project,
    new_todo,
    notification_message,
    run_pilot,
)
from todooit.api import BIN, Todo
from todooit.ui.tui import Todooit
from todooit.ui.widgets.bars import StatusBar


async def settle(pilot):
    """Waits out the jump a key that opens another pane sends the app on"""

    for _ in range(5):
        await pilot.pause()


def confirm_message(app: Todooit) -> Optional[str]:
    """The question the bar is holding the keyboard for, if it is asking one"""

    if app.bar_switcher.current != "confirm_bar":
        return None

    return app.bar_switcher.visible_content.message


async def test_the_status_bar_is_the_default():
    async with run_pilot() as pilot:
        app = await boot(pilot)

        assert app.bar_switcher.current == "status_bar"
        assert isinstance(app.bar_switcher.visible_content, StatusBar)
        assert not app.bar_switcher.is_focused


async def test_notifications_show_in_the_bar():
    async with run_pilot() as pilot:
        app = await boot(pilot)

        app.api.notify("hello from the test", "info")
        await pilot.pause()

        assert app.bar_switcher.current == "notification_bar"
        assert notification_message(app) == "hello from the test"

        # An info notification does not take the keyboard
        assert not app.bar_switcher.is_focused


async def test_confirm_bar_takes_the_keyboard_and_answers_no():
    async with run_pilot() as pilot:
        app = await boot(pilot)
        await new_project(pilot, "project")
        todo = await new_todo(pilot, "precious")

        # `yy` deletes for good, and that is the one edit that asks first
        await pilot.press("y", "y")
        await pilot.pause()

        assert app.bar_switcher.current == "confirm_bar"
        assert app.bar_switcher.is_focused

        # The question names the row rather than the keypress: by the time it
        # is answered the row can be off screen, or gone
        assert confirm_message(app) == r"Delete [b]precious[/b] for good? \[y/N]"

        # While the question stands, other keys are answers, not commands
        await pilot.press("n")
        await pilot.pause()

        assert todo in Todo.all()
        assert notification_message(app) == "Kept [b]precious[/b]"


async def test_confirm_bar_answers_yes():
    async with run_pilot() as pilot:
        app = await boot(pilot)
        await new_project(pilot, "project")
        await new_todo(pilot, "doomed")

        await pilot.press("y", "y")
        await pilot.pause()
        await pilot.press("y")
        await pilot.pause()

        assert Todo.all() == []
        assert notification_message(app) == "Deleted [b]doomed[/b]"


async def test_the_question_says_what_leaves_with_the_row():
    """
    A task with steps under it takes them with it, and nothing in the Bin
    afterwards can fetch any of them back -- so the question says so
    """

    async with run_pilot() as pilot:
        app = await boot(pilot)
        await new_project(pilot, "project")
        await new_todo(pilot, "whole thing")

        await pilot.press("N")
        await commit_line(pilot, "a step")
        await pilot.pause()

        # Back up to the task the step was filed under
        await pilot.press("k")
        await pilot.press("y", "y")
        await pilot.pause()

        message = confirm_message(app)
        assert message is not None
        assert "[b]whole thing[/b] and everything under it" in message


async def test_the_question_is_asked_of_a_binned_row_too():
    """
    `yy` in the Bin is the second half of a delete, and the pane it is pressed
    in is no part of the question: it still names the task about to be lost
    """

    async with run_pilot() as pilot:
        app = await boot(pilot)
        await new_project(pilot, "project")
        await new_todo(pilot, "thrown away")

        await pilot.press("x", "x")
        await pilot.pause()
        await pilot.press("g", "b")
        await settle(pilot)

        await pilot.press("y", "y")
        await pilot.pause()

        assert confirm_message(app) == r"Delete [b]thrown away[/b] for good? \[y/N]"

        await pilot.press("y")
        await pilot.pause()

        assert Todo.all() == []
        assert notification_message(app) == "Deleted [b]thrown away[/b]"


async def test_a_nameless_row_is_called_after_its_pane():
    """
    Clearing a project's name drops it, and one holding work asks first -- with
    nothing left to quote, so the question says what kind of thing is going
    """

    async with run_pilot() as pilot:
        app = await boot(pilot)
        await new_project(pilot, "doomed")

        await pilot.press("ö", "n")
        await commit_line(pilot, "work inside it")
        await pilot.press("j")

        # Empty the description and commit it
        await pilot.press("e", "c", "c")
        await pilot.press("enter")
        await pilot.pause()

        message = confirm_message(app)
        assert message is not None
        assert "this project and everything under it" in message


async def test_a_long_description_is_cut_short_in_the_question():
    """The bar has one line, and the front of a description is what names it"""

    async with run_pilot() as pilot:
        app = await boot(pilot)
        await new_project(pilot, "project")
        await new_todo(pilot, "w" * 80)

        await pilot.press("y", "y")
        await pilot.pause()

        message = confirm_message(app)
        assert message is not None
        assert "…" in message
        assert "w" * 80 not in message


async def test_emptying_the_bin_counts_what_goes_and_says_what_went():
    async with run_pilot() as pilot:
        app = await boot(pilot)
        await new_project(pilot, "project")
        await new_todo(pilot, "one")
        await pilot.press("x", "x")
        await pilot.pause()

        await pilot.press("g", "b")
        await pilot.pause()
        await pilot.press("Y", "Y")
        await pilot.pause()

        assert confirm_message(app) == r"Delete 1 task in the Bin for good? \[y/N]"

        await pilot.press("n")
        await pilot.pause()

        assert notification_message(app) == "Bin left as it was"
        assert len(BIN.todos) == 1

        await pilot.press("Y", "Y")
        await pilot.pause()
        await pilot.press("y")
        await pilot.pause()

        assert notification_message(app) == "Bin emptied — 1 task deleted"
        assert BIN.todos == []


async def test_field_bar_edits_a_hidden_column():
    """
    Editing the scheduled date from Today: the column is not drawn there,
    so the buffer goes to the bar instead of a column the pane does not have
    """

    async with run_pilot() as pilot:
        app = await boot(pilot)
        await create_and_move_to_todo(pilot)

        await pilot.press("n")
        await pilot.press(*list("planned work"))
        await pilot.press("enter")
        await pilot.pause()

        # Schedule it for today so the Today pane picks it up
        await pilot.press("s")
        await pilot.press(*list("today"))
        await pilot.press("enter")
        await pilot.pause()

        await pilot.press("g", "t")
        await pilot.pause()

        # An edit of the hidden column moves the buffer into the bar
        await pilot.press("s")
        await pilot.pause()

        assert app.bar_switcher.current == "field_bar"

        await pilot.press("ctrl+l")  # clear the buffer
        await pilot.press(*list("tomorrow"))
        await pilot.press("enter")
        await pilot.pause()

        from datetime import date, timedelta

        todo = Todo.all()[0]
        assert todo.scheduled is not None
        assert todo.scheduled.date() == date.today() + timedelta(days=1)


async def test_a_bar_widget_tick_survives_the_screen_going_away():
    """
    A tick that lands while the app is tearing down is let go, not raised

    A bar widget on a timer goes on ticking whatever else is happening, and
    the tick that arrives after the last screen has been popped used to take
    the whole app down with it: the redraw it asks for reaches for a bar that
    is no longer on any screen. Only the redraw is skipped; the value is still
    worked out and kept, since that half of the tick needs no screen at all.
    """

    async with run_pilot() as pilot:
        app = await boot(pilot)

        def tick(api):
            return "09:19:58"

        # Emptied by hand: mid-teardown is a window no test can land on
        # reliably, and waiting around for it is what made this a flake
        # rather than a failure
        stack = list(app._screen_stack)
        app._screen_stack.clear()

        try:
            app.api.config_manager._update_todooit_value(tick)
        finally:
            app._screen_stack.extend(stack)

        assert getattr(tick, "__todooit_value") == "09:19:58"


async def test_binning_says_where_it_went_and_how_to_get_back():
    """
    `xx` and `yy` both make a row vanish, and the pane cannot tell them apart:
    the bar is where the difference between them is said
    """

    async with run_pilot() as pilot:
        app = await boot(pilot)
        await new_project(pilot, "project")
        await new_todo(pilot, "off the list")

        await pilot.press("x", "x")
        await pilot.pause()

        assert notification_message(app) == (
            "Binned [b]off the list[/b] — [b]gb[/b] then [b]R[/b] puts it back"
        )
        assert Todo.all()[0].is_binned


async def test_dropping_a_project_points_at_the_tasks_it_left_behind():
    """
    The project row simply goes; what it was holding is what lands in the Bin,
    and restoring one of those is what builds the project again
    """

    async with run_pilot() as pilot:
        app = await boot(pilot)
        await new_project(pilot, "abandoned")
        await new_todo(pilot, "orphaned work")

        await pilot.press("j")  # back onto the project
        await pilot.press("x", "x")
        await pilot.pause()

        assert notification_message(app) == (
            "Dropped [b]abandoned[/b] — its tasks are in the Bin"
        )
        assert len(BIN.todos) == 1


async def test_dropping_an_empty_project_points_at_nothing():
    async with run_pilot() as pilot:
        app = await boot(pilot)
        await new_project(pilot, "never used")

        await pilot.press("x", "x")
        await pilot.pause()

        assert notification_message(app) == "Dropped [b]never used[/b]"
        assert BIN.todos == []


async def test_copying_a_description_says_the_key_landed():
    """A copy leaves nothing on screen, the same way the note beside it does"""

    async with run_pilot() as pilot:
        app = await boot(pilot)
        await new_project(pilot, "nixos")

        await pilot.press("ctrl+c")
        await pilot.pause()

        assert notification_message(app) == "Description copied to clipboard"


async def test_an_error_shows_a_copy_icon_and_a_warning_does_not():
    from todooit.ui.widgets.bars.notification_bar.bar import COPY_LABEL

    async with run_pilot() as pilot:
        app = await boot(pilot)

        app.api.notify("it broke", "error")
        await pilot.pause()
        assert COPY_LABEL in str(app.bar_switcher.visible_content.render_line(0).text)

        app.api.notify("careful", "warning")
        await pilot.pause()
        assert notification_message(app) == "careful"
        assert COPY_LABEL not in str(app.bar_switcher.visible_content.render_line(0).text)


async def test_errors_stay_up_longer_than_warnings():
    from todooit.ui.widgets.bars.notification_bar.bar import (
        COPIED_SHOWN_FOR,
        SHOWN_FOR,
    )

    assert SHOWN_FOR["error"] == 10
    assert COPIED_SHOWN_FOR == 2
    assert SHOWN_FOR["error"] > SHOWN_FOR["warning"] > SHOWN_FOR["info"]


async def test_clicking_an_error_copies_it_with_its_traceback():
    async with run_pilot() as pilot:
        app = await boot(pilot)

        def explode():
            raise ValueError("the [b]bad[/b] value")

        app.api.keys.set("Z", explode)
        await pilot.press("Z")
        await pilot.pause()
        assert notification_message(app) == "the [b]bad[/b] value"

        await pilot.click("NotificationBar")
        await pilot.pause()

        # Markup off, and the traceback under it
        assert app.clipboard.startswith("the bad value\n\nTraceback")
        assert "ValueError: the [b]bad[/b] value" in app.clipboard
        assert notification_message(app) == "Error copied to clipboard"
        assert app.bar_switcher.current == "notification_bar"
        assert "info" in app.bar_switcher.visible_content.classes
        assert "Copy" not in str(app.bar_switcher.visible_content.render_line(0).text)


async def test_clicking_an_error_without_a_traceback_copies_the_message():
    async with run_pilot() as pilot:
        app = await boot(pilot)

        app.api.notify("no [b]browser[/b] found", "error")
        await pilot.pause()
        await pilot.click("NotificationBar")
        await pilot.pause()

        assert app.clipboard == "no browser found"


async def test_clicking_a_warning_copies_nothing():
    async with run_pilot() as pilot:
        app = await boot(pilot)

        app.api.notify("careful", "warning")
        await pilot.pause()
        await pilot.click("NotificationBar")
        await pilot.pause()

        assert app.clipboard != "careful"
        assert notification_message(app) == "careful"
