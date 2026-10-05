"""
How often a recurring todo comes back

A count of one unit, written the way it is typed: `2h`, `3d`, `1w`, `1m`,
`1y`. There are no minutes, so `m` is a month (`mo` is read too). Months and
years are calendar steps, not a fixed length, so a monthly todo on the 5th
stays on the 5th.

A todo on a day a shorter month lacks lands on that month's last day and goes
back to its own day after: 31 Jan, 28 Feb, 31 Mar, 30 Apr. While it sits on
such a clamped day, the day it belongs on is kept in `day`.

`eom` is the month's last working day: the last weekday that is not an
Austrian public holiday. It has no count and no kept day; each month's is
worked out from the calendar.
"""

import re
from calendar import monthrange
from dataclasses import dataclass, replace
from datetime import date, datetime, timedelta
from typing import Optional, Tuple

from sqlalchemy import String
from sqlalchemy.types import TypeDecorator

from ..utils.holidays import next_month_end

# Typed suffix -> unit
UNITS = {
    "mo": "months",
    "m": "months",
    "h": "hours",
    "d": "days",
    "w": "weeks",
    "y": "years",
}

SUFFIXES = {"months": "m", "hours": "h", "days": "d", "weeks": "w", "years": "y"}

CALENDAR_UNITS = ("months", "years")

PATTERN = re.compile(r"^(\d+)(mo|m|h|d|w|y)(?:@(\d+))?$")

MONTH_END = "eom"

# Rows written before cadences were stored as text hold an SQLAlchemy Interval:
# the timedelta as a moment after the epoch
EPOCH = datetime(1970, 1, 1)


@dataclass(frozen=True)
class Cadence:
    count: int
    unit: str
    # Calendar units only: the day of the month a clamped date goes back to
    day: Optional[int] = None

    @classmethod
    def parse(cls, text: str) -> "Cadence":
        text = text.strip()

        if text.lower() == MONTH_END:
            return cls(1, MONTH_END)

        match = PATTERN.match(text)

        if match is None or int(match[1]) == 0:
            raise ValueError("Invalid recurrence format")

        day = int(match[3]) if match[3] else None
        return cls(int(match[1]), UNITS[match[2]], day)

    @classmethod
    def from_timedelta(cls, td: timedelta) -> "Cadence":
        """
        The largest unit that measures it exactly

        An old interval of whole minutes was typed as `Nm`, which now means
        N months, so that is what it becomes.
        """

        if td.seconds == 0 and td.days % 7 == 0:
            return cls(td.days // 7, "weeks")

        if td.seconds == 0:
            return cls(td.days, "days")

        minutes = int(td.total_seconds()) // 60

        if minutes % 60 == 0:
            return cls(minutes // 60, "hours")

        return cls(minutes, "months")

    def __str__(self) -> str:
        """As typed, without the kept day"""

        if self.unit == MONTH_END:
            return MONTH_END

        return f"{self.count}{SUFFIXES[self.unit]}"

    def stored(self) -> str:
        return f"{self}@{self.day}" if self.day else str(self)

    def first(self, when: datetime) -> datetime:
        """
        The first occurrence on or after `when`

        Any date starts a fixed or calendar cadence; a month end only starts
        on a month end.
        """

        if self.unit == MONTH_END:
            return _on(next_month_end(when.date()), when)

        return when

    def after(self, when: datetime) -> Tuple[datetime, "Cadence"]:
        """
        The next occurrence after `when`, and the cadence to keep for the one
        after it (which remembers a day the new date had to give up)
        """

        if self.unit == MONTH_END:
            return _on(next_month_end(when.date(), strictly_after=True), when), self

        if self.unit not in CALENDAR_UNITS:
            return when + timedelta(**{self.unit: self.count}), self

        # The kept day only holds while the date is still where it put it;
        # a todo moved by hand recurs on its new day
        day = self.day if self.day and _clamp(when, self.day) == when.day else when.day
        months = self.count * (12 if self.unit == "years" else 1)

        index = when.month - 1 + months
        year, month = when.year + index // 12, index % 12 + 1
        new = when.replace(year=year, month=month, day=1)
        new = new.replace(day=_clamp(new, day))

        return new, replace(self, day=day if day != new.day else None)


def _on(day: date, when: datetime) -> datetime:
    """`when`'s time of day, on another day"""

    return datetime.combine(day, when.time())


def _clamp(when: datetime, day: int) -> int:
    return min(day, monthrange(when.year, when.month)[1])


class CadenceType(TypeDecorator):
    """
    A cadence in the old Interval column, as its typed text

    No migration: SQLite keeps text as text in that column, and the old
    epoch-datetime rows are read as the fixed interval they always were.
    """

    impl = String
    cache_ok = True

    def process_bind_param(self, value: Optional[Cadence], dialect) -> Optional[str]:
        return None if value is None else value.stored()

    def process_result_value(self, value, dialect) -> Optional[Cadence]:
        if value is None:
            return None

        if isinstance(value, datetime):
            return Cadence.from_timedelta(value - EPOCH)

        if value == MONTH_END or PATTERN.match(value):
            return Cadence.parse(value)

        return Cadence.from_timedelta(datetime.fromisoformat(value) - EPOCH)
