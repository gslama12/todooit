from datetime import datetime

import pytest
from sqlalchemy import text

from todooit.api import Cadence, Todo, lifecycle, manager
from todooit.utils import next_month_end
from tests.test_core.core_base import *  # noqa: F401,F403


def advances(cadence: Cadence, start: datetime, times: int) -> list:
    dates = []

    for _ in range(times):
        start, cadence = cadence.after(start)
        dates.append(start.date().isoformat())

    return dates


@pytest.mark.parametrize(
    "typed, cadence",
    [
        ("2h", Cadence(2, "hours")),
        ("3d", Cadence(3, "days")),
        ("1w", Cadence(1, "weeks")),
        ("1m", Cadence(1, "months")),
        ("1y", Cadence(1, "years")),
    ],
)
def test_a_cadence_reads_and_shows_as_typed(typed, cadence):
    assert Cadence.parse(typed) == cadence
    assert str(cadence) == typed


@pytest.mark.parametrize("typed", ["", "1", "0d", "1x", "mo", "1 mo", "-1d"])
def test_a_malformed_cadence_is_refused(typed):
    with pytest.raises(ValueError):
        Cadence.parse(typed)


@pytest.mark.parametrize("typed", ["1m", "1mo"])
def test_m_is_a_month(typed):
    """The bug: `1m` was read as a minute"""

    assert Cadence.parse(typed) == Cadence(1, "months")
    assert str(Cadence.parse(typed)) == "1m"


def test_a_month_is_a_calendar_month_not_thirty_days():
    dates = advances(Cadence(1, "months"), datetime(2026, 1, 5), 3)

    assert dates == ["2026-02-05", "2026-03-05", "2026-04-05"]


def test_the_31st_takes_the_last_day_of_a_short_month_and_comes_back():
    dates = advances(Cadence(1, "months"), datetime(2026, 1, 31), 5)

    assert dates == [
        "2026-02-28",
        "2026-03-31",
        "2026-04-30",
        "2026-05-31",
        "2026-06-30",
    ]


def test_a_clamped_day_is_kept_until_it_fits_again():
    new, cadence = Cadence(1, "months").after(datetime(2026, 1, 31))

    assert new == datetime(2026, 2, 28)
    assert cadence == Cadence(1, "months", day=31)

    new, cadence = cadence.after(new)

    assert new == datetime(2026, 3, 31)
    assert cadence == Cadence(1, "months")


def test_the_30th_stays_the_30th_through_a_long_month():
    dates = advances(Cadence(1, "months"), datetime(2026, 9, 30), 2)

    assert dates == ["2026-10-30", "2026-11-30"]


def test_a_clamped_todo_moved_by_hand_recurs_on_its_new_day():
    clamped = Cadence(1, "months", day=31)

    new, cadence = clamped.after(datetime(2026, 2, 20))

    assert new == datetime(2026, 3, 20)
    assert cadence == Cadence(1, "months")


def test_a_leap_day_lands_on_the_28th_and_returns_in_a_leap_year():
    dates = advances(Cadence(1, "years"), datetime(2028, 2, 29), 4)

    assert dates == ["2029-02-28", "2030-02-28", "2031-02-28", "2032-02-29"]


def test_several_months_cross_the_year():
    dates = advances(Cadence(3, "months"), datetime(2026, 11, 30), 2)

    assert dates == ["2027-02-28", "2027-05-30"]


def test_a_fixed_cadence_keeps_the_time_of_day():
    new, cadence = Cadence(2, "hours").after(datetime(2026, 10, 5, 9))

    assert new == datetime(2026, 10, 5, 11)
    assert cadence == Cadence(2, "hours")


def reloaded(todo: Todo) -> Todo:
    manager.session.expire_all()
    return manager.session.get(Todo, todo.id)


def test_a_monthly_todo_completed_on_the_31st_comes_back_on_the_31st(create_project):
    rent = create_project().add_todo()
    rent.description = "Pay rent"
    rent.scheduled = datetime(2026, 1, 31)
    rent.recurrence = Cadence(1, "months")
    rent.save()

    outcome = lifecycle.complete(rent)
    rent = reloaded(rent)

    assert outcome.advanced_to == datetime(2026, 2, 28)
    assert rent.recurrence == Cadence(1, "months", day=31)

    lifecycle.complete(rent)
    rent = reloaded(rent)

    assert rent.is_pending
    assert rent.scheduled == datetime(2026, 3, 31)
    assert rent.recurrence == Cadence(1, "months")


@pytest.mark.parametrize(
    "stored, cadence",
    [
        ("1970-01-01 00:01:00.000000", Cadence(1, "months")),
        ("1970-01-01 00:03:00.000000", Cadence(3, "months")),
        ("1970-01-01 02:00:00.000000", Cadence(2, "hours")),
        ("1970-01-04 00:00:00.000000", Cadence(3, "days")),
        ("1970-01-15 00:00:00.000000", Cadence(2, "weeks")),
    ],
)
def test_a_recurrence_stored_before_months_reads_as_the_same_interval(
    create_project, stored, cadence
):
    """Older databases hold an Interval (a moment after the epoch); no migration needed. A minute interval was typed `Nm`, now N months"""

    todo = create_project().add_todo()
    todo.save()

    manager.session.execute(
        text("UPDATE todo SET recurrence = :stored WHERE id = :id"),
        {"stored": stored, "id": todo.id},
    )

    assert reloaded(todo).recurrence == cadence


@pytest.mark.parametrize("typed", ["eom", "EOM", " eom "])
def test_eom_reads_and_shows_as_eom(typed):
    assert Cadence.parse(typed) == Cadence(1, "eom")
    assert str(Cadence.parse(typed)) == "eom"


@pytest.mark.parametrize("typed", ["1eom", "eom@3", "eo"])
def test_eom_takes_no_count_or_day(typed):
    with pytest.raises(ValueError):
        Cadence.parse(typed)


def test_eom_recurs_on_each_months_last_working_day():
    """Oct 2026 ends on a Saturday, Jan 2027 on a Sunday"""

    dates = advances(Cadence(1, "eom"), datetime(2026, 9, 30), 4)

    assert dates == ["2026-10-30", "2026-11-30", "2026-12-31", "2027-01-29"]


def test_eom_skips_a_public_holiday_at_the_end_of_the_month():
    """31 May 2029 is Fronleichnam"""

    assert advances(Cadence(1, "eom"), datetime(2029, 4, 30), 1) == ["2029-05-30"]


def test_eom_from_mid_month_comes_this_month_and_keeps_the_time():
    new, cadence = Cadence(1, "eom").after(datetime(2026, 10, 5, 9))

    assert new == datetime(2026, 10, 30, 9)
    assert cadence == Cadence(1, "eom")


def test_eom_starts_on_a_month_end_and_other_cadences_anywhere():
    assert Cadence(1, "eom").first(datetime(2026, 10, 5)) == datetime(2026, 10, 30)
    assert Cadence(1, "eom").first(datetime(2026, 10, 30)) == datetime(2026, 10, 30)
    assert Cadence(1, "weeks").first(datetime(2026, 10, 5)) == datetime(2026, 10, 5)


def test_eom_is_stored_and_read_back(create_project):
    todo = create_project().add_todo()
    todo.scheduled = datetime(2026, 10, 30)
    todo.recurrence = Cadence(1, "eom")
    todo.save()

    assert reloaded(todo).recurrence == Cadence(1, "eom")


def test_setting_eom_moves_the_todo_onto_the_month_end(create_project):
    report = create_project().add_todo()
    report.scheduled = datetime(2026, 10, 5)
    report.save()

    lifecycle.set_recurrence(report, Cadence(1, "eom"))

    assert report.scheduled == datetime(2026, 10, 30)


def test_setting_eom_on_a_todo_with_a_deadline_starts_from_the_deadline(create_project):
    report = create_project().add_todo()
    report.due = datetime(2026, 11, 3)
    report.save()

    lifecycle.set_recurrence(report, Cadence(1, "eom"))

    assert report.due is None
    assert report.scheduled == datetime(2026, 11, 30)


def test_setting_eom_on_an_undated_todo_takes_this_months_end_at_midnight(
    create_project,
):
    report = create_project().add_todo()
    report.save()

    lifecycle.set_recurrence(report, Cadence(1, "eom"))

    assert report.scheduled == datetime.combine(
        next_month_end(datetime.now().date()), datetime.min.time()
    )


def test_completing_an_eom_todo_moves_it_to_next_months_end(create_project):
    report = create_project().add_todo()
    report.scheduled = datetime(2026, 10, 30)
    report.recurrence = Cadence(1, "eom")
    report.save()

    outcome = lifecycle.complete(report)
    report = reloaded(report)

    assert outcome.advanced_to == datetime(2026, 11, 30)
    assert report.is_pending
    assert report.recurrence == Cadence(1, "eom")
