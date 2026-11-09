"""
The calendar overlay: a day picked off a month instead of typed into a field
"""

from datetime import date, timedelta

from tests.test_ui.ui_base import (
    boot,
    commit_line,
    create_and_move_to_todo,
    new_todo,
    run_pilot,
    visible_todos,
)
from todooit.api import Todo
from todooit.ui.screens import MainScreen
from todooit.ui.screens.calendar import (
    HINT,
    WEEKS_DRAWN,
    CalendarScreen,
    add_months,
    weeks_around,
)

TODAY = date.today()


async def a_todo_being_dated(pilot, column_key: str = "s") -> CalendarScreen:
    """
    A task with one of its date fields open and the month up over it

    The whole of the path the feature is reached by: a task, the key that
    starts the edit, and the word that asks for a month instead of a date.
    """

    await create_and_move_to_todo(pilot)
    await new_todo(pilot, "file taxes")

    await pilot.press(column_key)
    await pilot.pause()
    await pilot.press(*list("cal"))
    await pilot.pause()

    screen = pilot.app.screen
    assert isinstance(screen, CalendarScreen)

    return screen


def the_todo() -> Todo:
    return Todo.all()[0]


async def test_the_month_opens_on_today():
    """A field holding nothing has no day to open on, so it opens on this one"""

    async with run_pilot() as pilot:
        await boot(pilot)
        screen = await a_todo_being_dated(pilot)

        assert screen._selected == TODAY
        assert screen._title == "Scheduled date"


async def test_the_word_is_taken_back_out_of_the_field():
    """
    "cal" is a question, not a value, so the field never holds it

    The month is opened on what the field held before the question was asked,
    and escaping back to the field finds that still there -- not three letters
    that are no date at all.
    """

    async with run_pilot() as pilot:
        app = await boot(pilot)
        await create_and_move_to_todo(pilot)
        await new_todo(pilot, "file taxes")

        await pilot.press("s")
        await commit_line(pilot, "5.9.2027")

        await pilot.press("s")
        await pilot.press(*list("cal"))
        await pilot.pause()

        screen = app.screen
        assert isinstance(screen, CalendarScreen)
        assert screen._selected == date(2027, 9, 5)

        await pilot.press("escape")
        await pilot.pause()

        # Straight back out of the edit: what the field hands back is what it
        # was holding, which is the date the word was typed over
        await pilot.press("enter")
        await pilot.pause()

        scheduled = the_todo().scheduled
        assert scheduled is not None
        assert scheduled.date() == date(2027, 9, 5)


async def test_the_direction_keys_walk_the_month():
    """`j`/`ö` a day either way and `k`/`l` a week, as everywhere else"""

    async with run_pilot() as pilot:
        await boot(pilot)
        screen = await a_todo_being_dated(pilot)

        await pilot.press("ö")
        assert screen._selected == TODAY + timedelta(days=1)

        await pilot.press("j")
        assert screen._selected == TODAY

        await pilot.press("l")
        assert screen._selected == TODAY + timedelta(days=7)

        await pilot.press("k")
        assert screen._selected == TODAY

        await pilot.press("right", "down")
        assert screen._selected == TODAY + timedelta(days=8)


async def test_the_shifted_keys_walk_whole_months():
    async with run_pilot() as pilot:
        await boot(pilot)
        screen = await a_todo_being_dated(pilot)

        await pilot.press("Ö")
        assert screen._selected == add_months(TODAY, 1)

        await pilot.press("J", "J")
        assert screen._selected == add_months(TODAY, -1)


async def test_t_comes_back_to_today():
    async with run_pilot() as pilot:
        await boot(pilot)
        screen = await a_todo_being_dated(pilot)

        await pilot.press("Ö", "Ö", "ö")
        assert screen._selected != TODAY

        await pilot.press("t")
        assert screen._selected == TODAY


async def test_enter_keeps_the_day():
    """
    The pick settles the edit as well, the way typing the date and pressing
    enter would have: one confirmation, not two
    """

    async with run_pilot() as pilot:
        app = await boot(pilot)
        await a_todo_being_dated(pilot)

        await pilot.press("ö")
        await pilot.press("enter")
        await pilot.pause()

        todo = the_todo()
        assert todo.scheduled is not None
        assert todo.scheduled.date() == TODAY + timedelta(days=1)

        assert isinstance(app.screen, MainScreen)
        assert app.todooit_mode == "NORMAL"
        assert not visible_todos(app).is_editing


async def test_escape_goes_back_to_the_field():
    """
    The window closes onto the edit it was opened out of, not out of it

    Nothing has been picked, so nothing is written; the field is still being
    typed into and can still be typed into.
    """

    async with run_pilot() as pilot:
        app = await boot(pilot)
        await a_todo_being_dated(pilot)

        await pilot.press("ö")
        await pilot.press("escape")
        await pilot.pause()

        assert isinstance(app.screen, MainScreen)
        assert visible_todos(app).is_editing
        assert the_todo().scheduled is None

        await commit_line(pilot, "tom")
        assert the_todo().scheduled is not None


async def test_a_time_the_task_already_carries_is_kept():
    """
    The month has a day to say and nothing else, so the hour survives it
    """

    async with run_pilot() as pilot:
        await boot(pilot)
        await create_and_move_to_todo(pilot)
        await new_todo(pilot, "file taxes")

        await pilot.press("s")
        await commit_line(pilot, "tom 16:00")

        await pilot.press("s")
        await pilot.press(*list("cal"))
        await pilot.pause()

        await pilot.press("ö")
        await pilot.press("enter")
        await pilot.pause()

        todo = the_todo()
        assert todo.scheduled is not None
        assert todo.scheduled.date() == TODAY + timedelta(days=2)
        assert (todo.scheduled.hour, todo.scheduled.minute) == (16, 0)


async def test_the_due_date_asks_the_same_way():
    async with run_pilot() as pilot:
        await boot(pilot)
        screen = await a_todo_being_dated(pilot, column_key="d")

        assert screen._title == "Due date"

        await pilot.press("l")
        await pilot.press("enter")
        await pilot.pause()

        todo = the_todo()
        assert todo.due is not None
        assert todo.due.date() == TODAY + timedelta(days=7)


async def test_a_field_that_is_no_date_reads_the_word_as_a_word():
    """
    There is no month behind a description, so "cal" there is just text

    Nothing is turned away and nothing pops up: the three letters go into the
    buffer the way any other three would, and are kept.
    """

    async with run_pilot() as pilot:
        app = await boot(pilot)
        await create_and_move_to_todo(pilot)
        await new_todo(pilot, "file taxes")

        await pilot.press("e", "c", "c")
        await pilot.press(*list("cal"))
        await pilot.pause()

        assert isinstance(app.screen, MainScreen)

        await pilot.press("enter")
        await pilot.pause()

        assert the_todo().description == "cal"


async def test_the_word_is_read_whatever_it_is_typed_in():
    """Shouted or not, it is the same question"""

    async with run_pilot() as pilot:
        app = await boot(pilot)
        await create_and_move_to_todo(pilot)
        await new_todo(pilot, "file taxes")

        await pilot.press("s")
        await pilot.press(*list("CAL"))
        await pilot.pause()

        assert isinstance(app.screen, CalendarScreen)


def test_a_month_jump_stays_inside_the_month_it_lands_in():
    """The 31st of a month before a short one comes down on the last day there is"""

    assert add_months(date(2026, 1, 31), 1) == date(2026, 2, 28)
    assert add_months(date(2026, 12, 15), 1) == date(2027, 1, 15)
    assert add_months(date(2026, 1, 15), -1) == date(2025, 12, 15)


async def test_the_month_draws_whole_weeks():
    """
    Seven cells a row, the days either side of the month filling them out

    A week with a hole in it reads as a week missing something, so the month
    opens and closes on days of the months beside it rather than on blanks.
    """

    async with run_pilot() as pilot:
        await boot(pilot)
        screen = await a_todo_being_dated(pilot)

        weeks = screen._weeks()

        assert len(weeks) == WEEKS_DRAWN
        assert all(len(week) == 7 for week in weeks)
        assert all(week[0].weekday() == 0 for week in weeks)
        assert any(day == screen._selected for week in weeks for day in week)


def test_the_block_is_the_same_size_whatever_the_month():
    """
    The window may not grow or shrink under a cursor walking through it

    A month runs to four, five or six weeks depending on the day it opens on,
    and a panel sized to that would change height at the very moment the eye
    is following one cell across the screen. Every month is drawn in the same
    block instead, the short ones filled out with the days either side.
    """

    for year in range(2024, 2031):
        for month in range(1, 13):
            weeks = weeks_around(date(year, month, 1))

            assert len(weeks) == WEEKS_DRAWN
            assert all(len(week) == 7 for week in weeks)


def test_the_block_holds_the_day_it_was_asked_about():
    """
    February 2027 is four weeks exactly, August 2026 spills into six

    Whichever it is, the day the window is standing on has a cell of its own
    somewhere in the block, and the block runs as one unbroken stretch of days.
    """

    for probe in (date(2027, 2, 10), date(2026, 8, 31), date(2026, 9, 1)):
        days = [day for week in weeks_around(probe) for day in week]

        assert probe in days
        assert days == [days[0] + timedelta(days=step) for step in range(len(days))]
        assert days[0].weekday() == 0


def test_the_hint_names_only_what_the_window_adds():
    """
    The direction keys are the app's own and are not taught again here

    What the window is asked to say is the three that are new: the jump back
    to today, the way out, and the way to keep what is under the cursor.
    """

    for named in ("today", "esc", "enter"):
        assert named in HINT

    # The keys the panes themselves are walked with, named nowhere here
    for walked in ("jö", "kl", "JÖ", "week"):
        assert walked not in HINT

    # And it all fits on the one line the panel has room for
    assert "\n" not in HINT


async def test_the_app_is_not_being_typed_into_behind_the_window():
    """
    Every key belongs to the month while it is up

    "n" is a new task everywhere else in the app, and "q" quits; neither may
    reach past the window to the panes underneath.
    """

    async with run_pilot() as pilot:
        app = await boot(pilot)
        screen = await a_todo_being_dated(pilot)

        before = len(Todo.all())

        await pilot.press("n", "q")
        await pilot.pause()

        assert app.is_running
        assert app.screen is screen
        assert len(Todo.all()) == before


async def test_it_reaches_a_column_the_pane_does_not_draw():
    """
    Today leaves the scheduled column out, so that edit runs through the bar

    The calendar is asked for and answered the same way from there, and the
    bar is handed back afterwards rather than being left standing over an
    edit that is already over.
    """

    async with run_pilot() as pilot:
        app = await boot(pilot)
        await create_and_move_to_todo(pilot)
        await new_todo(pilot, "planned work")

        await pilot.press("s")
        await commit_line(pilot, "today")

        await pilot.press("g", "t")
        await pilot.pause()

        await pilot.press("s")
        await pilot.pause()
        assert app.bar_switcher.current == "field_bar"

        await pilot.press(*list("cal"))
        await pilot.pause()

        screen = app.screen
        assert isinstance(screen, CalendarScreen)
        assert screen._selected == TODAY

        await pilot.press("ö")
        await pilot.press("enter")
        await pilot.pause()

        todo = the_todo()
        assert todo.scheduled is not None
        assert todo.scheduled.date() == TODAY + timedelta(days=1)

        assert app.bar_switcher.current == "status_bar"
        assert app.todooit_mode == "NORMAL"


async def test_a_picked_day_is_taken_back_like_a_typed_one():
    """
    The pick is one step of the history, not a change nothing can undo

    The window settles the edit by sending the app the very enter a hand would
    have pressed, so it has to go the whole way that enter goes -- as far as
    the snapshot the undo stack is built out of, which is taken once the key
    has been handed on and not before.
    """

    async with run_pilot() as pilot:
        await boot(pilot)
        await create_and_move_to_todo(pilot)
        await new_todo(pilot, "file taxes")

        await pilot.press("s")
        await commit_line(pilot, "5.9.2027")

        await pilot.press("s")
        await pilot.press(*list("cal"))
        await pilot.pause()

        await pilot.press("ö")
        await pilot.press("enter")
        await pilot.pause()

        picked = the_todo().scheduled
        assert picked is not None
        assert picked.date() == date(2027, 9, 6)

        await pilot.press("u")
        await pilot.pause()
        await pilot.pause()

        back = the_todo().scheduled
        assert back is not None
        assert back.date() == date(2027, 9, 5)

        await pilot.press("ctrl+r")
        await pilot.pause()
        await pilot.pause()

        again = the_todo().scheduled
        assert again is not None
        assert again.date() == date(2027, 9, 6)
