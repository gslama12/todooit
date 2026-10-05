"""Calendar overlay for picking a day, opened by typing `cal` into a date field.

Walked with the app's direction keys: day/week steps and whole-month jumps.
Uses Austrian German month names, Monday-first weeks, and marks public holidays.
"""

from calendar import monthrange
from datetime import date, timedelta
from typing import Callable, List, Optional

from rich.console import Group
from rich.style import Style
from rich.table import Table
from rich.text import Text
from textual import events
from textual.app import ComposeResult
from textual.screen import ModalScreen
from textual.widgets import Static

from todooit.api.theme import TodooitThemeBase
from todooit.utils import WEEKDAY_NAMES, blend, day_label, holiday_name

from .base import BaseScreen
from .panel import HINT_GAP

# Spelled out rather than left to `%B`, which follows the process locale and
# would give English names by default. Austrian German: Jänner, not Januar.
MONTH_NAMES = (
    "Jänner",
    "Februar",
    "März",
    "April",
    "Mai",
    "Juni",
    "Juli",
    "August",
    "September",
    "Oktober",
    "November",
    "Dezember",
)

# Window title per column: which of the two dates is being picked
COLUMN_TITLES = {
    "due": "Due date",
    "scheduled": "Scheduled date",
}


def calendar_title(column: str) -> str:
    """Window title for the calendar opened over a column."""

    return COLUMN_TITLES.get(column, column.capitalize())


# Monday first, which is what the weekday names are already indexed by
WEEK_START = 0

SATURDAY = 5

# Fade for days from the adjacent month, shown only to fill out the week
OUTSIDE_FADE = 0.7

# Fade for a weekend inside the month: pickable, just not a workday
WEEKEND_FADE = 0.35

# Two digits plus the space either side
CELL_WIDTH = 4

# A month runs 4-6 weeks; always drawing 6 keeps the panel a fixed size so it
# doesn't resize while the cursor is walked across a month boundary. Short
# months are filled with real (faded) days from the neighboring months.
WEEKS_DRAWN = 6


def weeks_around(day: date) -> List[List[date]]:
    """Fixed block of WEEKS_DRAWN weeks, Monday first, starting on/before the 1st."""

    first = day.replace(day=1)
    start = first - timedelta(days=(first.weekday() - WEEK_START) % 7)

    return [
        [start + timedelta(days=week * 7 + weekday) for weekday in range(7)]
        for week in range(WEEKS_DRAWN)
    ]


# Only the keys this window adds; direction keys are already known app-wide.
# "back" not "cancel": escape hands the field back mid-edit, doesn't discard it.
HINT = HINT_GAP.join(("t today", "esc back", "enter pick"))

# A day stepping off the end of the month rolls into the next one
DAY_STEPS = {
    "j": -1,
    "left": -1,
    "ö": 1,
    "right": 1,
    "k": -7,
    "up": -7,
    "l": 7,
    "down": 7,
}

MONTH_STEPS = {
    "J": -1,
    "pageup": -1,
    "Ö": 1,
    "pagedown": 1,
}


def add_months(day: date, months: int) -> date:
    """Same day N months away, clamped to the last day if the target month is shorter."""

    month_index = day.month - 1 + months
    year = day.year + month_index // 12
    month = month_index % 12 + 1

    return date(year, month, min(day.day, monthrange(year, month)[1]))


class CalendarScreen(BaseScreen, ModalScreen):
    """Month overlay to pick a day from, over a dimmed copy of the app."""

    def __init__(self, title: str, initial: Optional[date] = None) -> None:
        super().__init__()

        self._title = title  # shown in the border
        self._selected = initial or date.today()  # cursor starts on the field's value, or today

    @property
    def theme(self) -> TodooitThemeBase:
        return self.api.vars.theme

    @property
    def panel(self) -> Static:
        return self.query_one("#calendar-panel", Static)

    def compose(self) -> ComposeResult:
        yield Static(id="calendar-panel")
        yield Static(HINT, id="calendar-hint")

    def on_mount(self) -> None:
        self.panel.border_title = self._title
        self._redraw()

    # ------------------------------------------------------------------
    # Walking the month
    # ------------------------------------------------------------------

    async def handle_key(self, event: events.Key) -> bool:
        # Modal owns every key; the app's bindings are for the panes behind it
        event.stop()

        key = self.resolve_key(event)

        if key == "escape":
            self.dismiss(None)
            return True

        if key == "enter":
            self.dismiss(self._selected)
            return True

        if key in DAY_STEPS:
            self._step(lambda: self._selected + timedelta(days=DAY_STEPS[key]))

        elif key in MONTH_STEPS:
            self._step(lambda: add_months(self._selected, MONTH_STEPS[key]))

        elif key == "t":
            self._move(date.today())

        return True

    def _step(self, to: Callable[[], date]) -> None:
        """Take a step unless it (or the week block around it) overflows `date`'s range.

        Caught here rather than in the redraw, so holding a key near year 1/9999
        just stops instead of crashing.
        """

        try:
            day = to()
            weeks_around(day)
        except (OverflowError, ValueError):
            return

        self._move(day)

    def _move(self, day: date) -> None:
        self._selected = day
        self._redraw()

    # ------------------------------------------------------------------
    # Drawing
    # ------------------------------------------------------------------

    def _redraw(self) -> None:
        # Blank line keeps the footer from reading as an eighth row of the month
        self.panel.update(
            Group(self._heading(), self._month(), Text(""), self._footer())
        )

    def _heading(self) -> Text:
        """The month being looked at, over the middle of the week it rules"""

        return Text(
            f"{MONTH_NAMES[self._selected.month - 1]} {self._selected.year}",
            style=Style(color=self.theme.primary, bold=True),
            justify="center",
        )

    def _month(self) -> Table:
        """Weeks of the month, Monday first, each day in its own cell."""

        # Not expanded: a week stays 7 cells wide regardless of the panel's width
        table = Table.grid()

        for _ in WEEKDAY_NAMES:
            table.add_column(width=CELL_WIDTH, justify="center")

        heading = Style(
            color=blend(self.theme.foreground1, self.theme.background2, OUTSIDE_FADE),
            bold=True,
        )

        table.add_row(*(Text(name, style=heading) for name in WEEKDAY_NAMES))

        for week in self._weeks():
            table.add_row(*(self._cell(day) for day in week))

        return table

    def _weeks(self) -> List[List[date]]:
        """Block of weeks the current month is read in."""

        return weeks_around(self._selected)

    def _cell(self, day: date) -> Text:
        """One day, styled as picked, today, a holiday, or a weekend (picked wins)."""

        # Padded to 2 digits, unjustified (a Text's own justify would override the
        # column's), so every cell and the selection pill are the same width
        label = Text(f"{day.day:2d}")

        if day == self._selected:
            label.stylize(
                Style(
                    color=self.theme.background1,
                    bgcolor=self.theme.primary,
                    bold=True,
                )
            )
        else:
            label.stylize(self._day_style(day))

        return label

    def _day_style(self, day: date) -> Style:
        if day == date.today():
            color, bold = self.theme.yellow, True

        elif holiday_name(day) is not None:
            color, bold = self.theme.red, False

        elif day.weekday() >= SATURDAY:
            color, bold = (
                blend(self.theme.foreground1, self.theme.background2, WEEKEND_FADE),
                False,
            )

        else:
            color, bold = self.theme.foreground3, False

        # Days from other months are always faded, regardless of other styling
        if day.month != self._selected.month:
            color = blend(color, self.theme.background2, OUTSIDE_FADE)
            bold = False

        return Style(color=color, bold=bold)

    def _footer(self) -> Group:
        """Selected day's label plus its holiday name, if any.

        Always two lines (holiday line blank when not a holiday) so the panel
        doesn't resize depending on whether the day has one.
        """

        date_line = Text(
            day_label(self._selected),
            style=Style(color=self.theme.foreground3),
            justify="center",
            no_wrap=True,
            overflow="ellipsis",
        )

        holiday_line = Text(
            holiday_name(self._selected) or "",
            style=Style(color=self.theme.red, bold=True),
            justify="center",
            no_wrap=True,
            overflow="ellipsis",
        )

        return Group(date_line, holiday_line)
