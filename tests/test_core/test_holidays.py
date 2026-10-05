"""
The Austrian public holidays the calendar marks
"""

from datetime import date

from todooit.utils import holiday_name, holidays, last_working_day, next_month_end


def test_the_fixed_ones_are_where_they_always_are():
    assert holiday_name(date(2026, 1, 1)) == "Neujahr"
    assert holiday_name(date(2026, 10, 26)) == "Nationalfeiertag"
    assert holiday_name(date(2026, 12, 26)) == "Stefanitag"


def test_the_movable_ones_follow_easter():
    """
    Easter 2026 is the 5th of April, and four holidays are counted off it
    """

    assert holiday_name(date(2026, 4, 6)) == "Ostermontag"
    assert holiday_name(date(2026, 5, 14)) == "Christi Himmelfahrt"
    assert holiday_name(date(2026, 5, 25)) == "Pfingstmontag"
    assert holiday_name(date(2026, 6, 4)) == "Fronleichnam"


def test_they_move_with_the_year():
    """Easter 2027 is the 28th of March, so Easter Monday is the 29th"""

    assert holiday_name(date(2027, 3, 29)) == "Ostermontag"
    assert holiday_name(date(2027, 4, 6)) is None


def test_an_ordinary_day_is_nothing_in_particular():
    assert holiday_name(date(2026, 9, 17)) is None


def test_easter_sunday_is_left_out():
    """
    It is a Sunday, and the calendar already draws a Sunday as a day off

    Whit Sunday, seven weeks later, is left out for the same reason.
    """

    assert holiday_name(date(2026, 4, 5)) is None
    assert holiday_name(date(2026, 5, 24)) is None


def test_a_year_holds_the_thirteen_there_are():
    assert len(holidays(2026)) == 13


def test_the_last_working_day_skips_the_weekend():
    """31 October 2026 is a Saturday"""

    assert last_working_day(2026, 10) == date(2026, 10, 30)
    assert last_working_day(2026, 9) == date(2026, 9, 30)


def test_the_last_working_day_skips_a_public_holiday():
    """31 May 2029 is a Thursday, and Fronleichnam"""

    assert last_working_day(2029, 5) == date(2029, 5, 30)


def test_a_month_end_already_missed_is_next_months():
    assert next_month_end(date(2026, 10, 5)) == date(2026, 10, 30)
    assert next_month_end(date(2026, 10, 30)) == date(2026, 10, 30)
    assert next_month_end(date(2026, 10, 31)) == date(2026, 11, 30)
    assert next_month_end(date(2026, 10, 30), strictly_after=True) == date(2026, 11, 30)
    assert next_month_end(date(2026, 12, 31), strictly_after=True) == date(2027, 1, 29)
