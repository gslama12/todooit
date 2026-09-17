"""
The Austrian public holidays, worked out rather than written down

A day picked off the calendar is a day meant to be worked on, and the ones
everything is shut are worth seeing before the pick rather than after it. Nine
of the thirteen sit on the same date every year; the other four are counted off
Easter, which moves, so a year is computed the first time it is drawn and kept
for as long as the calendar stays open.

Easter Sunday and Whit Sunday are left out on purpose: both are Sundays, and
the calendar already draws a Sunday as a day off.
"""

from datetime import date, timedelta
from functools import lru_cache
from typing import Mapping, Optional

from dateutil.easter import easter

# (month, day) -> name, for the holidays that never move
FIXED_HOLIDAYS = {
    (1, 1): "Neujahr",
    (1, 6): "Heilige Drei Könige",
    (5, 1): "Staatsfeiertag",
    (8, 15): "Mariä Himmelfahrt",
    (10, 26): "Nationalfeiertag",
    (11, 1): "Allerheiligen",
    (12, 8): "Mariä Empfängnis",
    (12, 25): "Christtag",
    (12, 26): "Stefanitag",
}

# Days after Easter Sunday -> name, for the ones that follow it around
EASTER_HOLIDAYS = {
    1: "Ostermontag",
    39: "Christi Himmelfahrt",
    50: "Pfingstmontag",
    60: "Fronleichnam",
}


@lru_cache(maxsize=16)
def holidays(year: int) -> Mapping[date, str]:
    """
    Every Austrian public holiday in a year, by the day it falls on

    Cached per year and handed out as it is, so nothing that reads it may
    write into it: a month that is scrolled past and come back to is drawn
    from this very same mapping.
    """

    days = {
        date(year, month, day): name for (month, day), name in FIXED_HOLIDAYS.items()
    }

    easter_sunday = easter(year)

    for offset, name in EASTER_HOLIDAYS.items():
        days[easter_sunday + timedelta(days=offset)] = name

    return days


def holiday_name(day: date) -> Optional[str]:
    """What the day is called, or None on a day that is nothing in particular"""

    return holidays(day.year).get(day)
