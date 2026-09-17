"""
The Austrian public holidays the calendar marks
"""

from datetime import date

from todooit.utils import holiday_name, holidays


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
