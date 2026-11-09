"""
Completing from the tree: the lifecycle's outcome is what the user sees

An advanced row flashes (it stays where it was, so nothing else shows that
something happened) and the status bar says what the completion meant.
"""

from datetime import date, timedelta

from tests.test_ui.ui_base import (
    commit_line,
    create_and_move_to_todo,
    flashed,
    notification_message,
    run_pilot,
)
from todooit.api import Cadence, Todo, manager
from todooit.utils import next_month_end
from todooit.utils.default_config import todo_recurrence_formatter


async def test_completing_a_recurring_todo_flashes_it_and_names_its_new_day():
    async with run_pilot() as pilot:
        tree = await create_and_move_to_todo(pilot)

        await pilot.press("n")
        await commit_line(pilot, "Weekly review")
        await pilot.press("s")
        await commit_line(pilot, "today")
        await pilot.press("r")
        await commit_line(pilot, "1w")

        review = tree.current_model
        assert isinstance(review, Todo)

        with flashed() as flashes:
            await pilot.press("c")
            await pilot.pause()

        next_week = date.today() + timedelta(weeks=1)
        day = f"{next_week:%a} {next_week.day} {next_week:%b}"

        assert review.is_pending
        assert (tree.id, review.uuid) in flashes
        assert notification_message(pilot.app) == f"advanced to {day}"


async def test_a_monthly_todo_typed_as_1m_advances_a_calendar_month():
    """`1m` is a month, not a minute"""

    async with run_pilot() as pilot:
        tree = await create_and_move_to_todo(pilot)

        await pilot.press("n")
        await commit_line(pilot, "Billing request")
        await pilot.press("s")
        await commit_line(pilot, "2026-01-31")
        await pilot.press("r")
        await commit_line(pilot, "1m")

        bills = tree.current_model
        assert isinstance(bills, Todo)
        assert bills.recurrence == Cadence(1, "months")

        await pilot.press("c")
        await pilot.pause()

        assert bills.scheduled.date() == date(2026, 2, 28)
        assert notification_message(pilot.app) == "advanced to Sat 28 Feb"


async def test_completing_a_todo_that_ends_recurrences_says_so():
    async with run_pilot() as pilot:
        tree = await create_and_move_to_todo(pilot)

        await pilot.press("n")
        await commit_line(pilot, "Garden season")
        garden = tree.current_model
        assert isinstance(garden, Todo)

        # A step that recurs on its own, written straight to the model
        water = garden.add_todo()
        water.description = "Water plants"
        water.recurrence = Cadence(3, "days")
        water.save()

        with flashed() as flashes:
            await pilot.press("c")
            await pilot.pause()

        assert garden.is_completed
        assert water.recurrence is None
        assert (tree.id, garden.uuid) not in flashes
        assert notification_message(pilot.app) == "recurrence ended on 1 step"


async def test_scheduling_a_parent_in_its_column_says_which_steps_moved():
    """The Scheduled column goes through the lifecycle (the floor)"""

    async with run_pilot() as pilot:
        tree = await create_and_move_to_todo(pilot)

        await pilot.press("n")
        await commit_line(pilot, "Tax return")
        tax = tree.current_model
        assert isinstance(tax, Todo)

        receipts = tax.add_todo()
        receipts.description = "Collect receipts"
        receipts.save()

        await pilot.press("s")
        await commit_line(pilot, "today")

        assert tax.scheduled is not None
        assert receipts.scheduled == tax.scheduled
        assert notification_message(pilot.app) == "1 step moved with it"


async def test_clearing_a_parents_date_in_its_column_clears_the_steps_on_it():
    """Steps on the parent's date follow it, down to having none"""

    async with run_pilot() as pilot:
        tree = await create_and_move_to_todo(pilot)

        await pilot.press("n")
        await commit_line(pilot, "Tax return")
        tax = tree.current_model
        assert isinstance(tax, Todo)

        receipts = tax.add_todo()
        receipts.description = "Collect receipts"
        receipts.save()

        await pilot.press("s")
        await commit_line(pilot, "today")
        assert receipts.scheduled == tax.scheduled

        await pilot.press("s", "ctrl+u")
        await commit_line(pilot, "")

        assert tax.scheduled is None
        assert receipts.scheduled is None
        assert notification_message(pilot.app) == "1 step unscheduled"


async def test_setting_a_parents_due_date_in_its_column_says_which_steps_moved():
    """The Due column goes through the lifecycle (the ceiling)"""

    async with run_pilot() as pilot:
        tree = await create_and_move_to_todo(pilot)

        await pilot.press("n")
        await commit_line(pilot, "Tax return")
        tax = tree.current_model
        assert isinstance(tax, Todo)

        receipts = tax.add_todo()
        receipts.description = "Collect receipts"
        receipts.save()

        await pilot.press("d")
        await commit_line(pilot, "today")

        assert tax.due is not None
        assert receipts.due == tax.due
        today = date.today()
        assert notification_message(pilot.app) == (
            f"1 step now due {today:%a} {today.day} {today:%b}"
        )


async def test_a_step_due_after_its_parent_is_refused_with_a_warning():
    """Never due after the parent, story 51: a rule, not a crash; the old value stays"""

    async with run_pilot() as pilot:
        tree = await create_and_move_to_todo(pilot)

        await pilot.press("n")
        await commit_line(pilot, "Tax return")
        await pilot.press("d")
        await commit_line(pilot, "today")
        tax = tree.current_model
        assert isinstance(tax, Todo)

        await pilot.press("N")
        await commit_line(pilot, "File online")
        filing = tree.current_model
        assert isinstance(filing, Todo) and filing.parent_todo is tax
        old = filing.due

        await pilot.press("d")
        await commit_line(pilot, "in 2 weeks")

        assert filing.due == old
        assert pilot.app.bar_switcher.visible_content.level == "warning"
        assert notification_message(pilot.app).startswith(
            "Can't be due after its parent's due date"
        )

        # The field shows what is stored, not what was refused
        await pilot.press("d")
        assert tree.current.editing == "due"
        assert tree.current._get_component("due").value == (
            "" if old is None else f"{old:%d.%m.%Y}"
        )


async def test_a_recurrence_under_a_recurring_parent_is_refused_with_a_warning():
    """One cadence per line, story 16: a rule, not a crash; the old value stays"""

    async with run_pilot() as pilot:
        tree = await create_and_move_to_todo(pilot)

        await pilot.press("n")
        await commit_line(pilot, "Weekly review")
        await pilot.press("r")
        await commit_line(pilot, "1w")

        await pilot.press("N")
        await commit_line(pilot, "Pay rent")
        rent = tree.current_model
        assert isinstance(rent, Todo) and rent.parent_todo is not None

        await pilot.press("r")
        await commit_line(pilot, "4w")

        assert rent.recurrence is None
        assert pilot.app.bar_switcher.visible_content.level == "warning"
        assert notification_message(pilot.app) == (
            'Can\'t recur: its ancestor "Weekly review" already recurs'
        )

        # The field shows what is stored, not what was refused
        await pilot.press("r")
        assert tree.current.editing == "recurrence"
        assert tree.current._get_component("recurrence").value == ""


async def test_a_recurrence_on_a_parent_says_which_step_recurrences_it_ended():
    """One cadence per line, story 15: wiped recurrences below are named in the status bar"""

    async with run_pilot() as pilot:
        tree = await create_and_move_to_todo(pilot)

        await pilot.press("n")
        await commit_line(pilot, "Garden season")
        garden = tree.current_model
        assert isinstance(garden, Todo)

        await pilot.press("N")
        await commit_line(pilot, "Water plants")
        await pilot.press("r")
        await commit_line(pilot, "3d")
        water = tree.current_model
        assert isinstance(water, Todo) and water.recurrence == Cadence(3, "days")

        await pilot.press("k")
        assert tree.current_model is garden
        await pilot.press("r")
        await commit_line(pilot, "1w")

        assert garden.recurrence == Cadence(1, "weeks")
        assert water.recurrence is None
        assert notification_message(pilot.app) == "recurrence ended on 1 step"


async def indent_stretch_under_weekly_review(pilot):
    """A daily "Stretch" indented (`I`) under a weekly "Weekly review" """

    tree = await create_and_move_to_todo(pilot)

    await pilot.press("n")
    await commit_line(pilot, "Weekly review")
    await pilot.press("r")
    await commit_line(pilot, "1w")
    review = tree.current_model

    await pilot.press("n")
    await commit_line(pilot, "Stretch")
    await pilot.press("r")
    await commit_line(pilot, "1d")
    stretch = tree.current_model
    assert isinstance(stretch, Todo) and stretch.recurrence == Cadence(1, "days")

    await pilot.press("I")
    await pilot.pause()

    return review, stretch


async def test_an_indent_that_overrides_something_says_so():
    """Becoming a step is fitted, stories 37-38: fitted rather than refused, and told"""

    async with run_pilot() as pilot:
        review, stretch = await indent_stretch_under_weekly_review(pilot)

        assert stretch.parent_todo is review
        assert stretch.recurrence is None
        assert pilot.app.bar_switcher.visible_content.level == "info"
        assert notification_message(pilot.app) == "stopped recurring"


async def test_one_undo_takes_back_an_indent_and_its_overrides():
    """Story 52: fitting is never a one-way door"""

    async with run_pilot() as pilot:
        review, stretch = await indent_stretch_under_weekly_review(pilot)

        await pilot.press("u")
        await pilot.pause()
        await pilot.pause()

        manager.session.expire_all()
        assert stretch.parent_todo is None
        assert stretch.parent_project is review.parent_project
        assert stretch.recurrence == Cadence(1, "days")


async def test_typing_eom_recurs_on_the_month_end_and_shows_eom():
    async with run_pilot() as pilot:
        tree = await create_and_move_to_todo(pilot)

        await pilot.press("n")
        await commit_line(pilot, "Monthly report")
        report = tree.current_model
        assert isinstance(report, Todo)

        await pilot.press("r")
        await commit_line(pilot, "eom")

        assert report.recurrence == Cadence(1, "eom")
        assert report.scheduled is not None
        assert report.scheduled.date() == next_month_end(date.today())
        assert todo_recurrence_formatter(report.recurrence, report) == "eom"

        await pilot.press("r")
        assert tree.current._get_component("recurrence").value == "eom"


async def test_typing_eom_as_a_due_date_takes_the_last_working_day():
    async with run_pilot() as pilot:
        tree = await create_and_move_to_todo(pilot)

        await pilot.press("n")
        await commit_line(pilot, "Hand in timesheet")
        sheet = tree.current_model
        assert isinstance(sheet, Todo)

        await pilot.press("d")
        await commit_line(pilot, "eom")

        assert sheet.due is not None
        assert sheet.due.date() == next_month_end(date.today())
