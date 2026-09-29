"""
The calendar overlay: a month to pick a day off, instead of typing one

Both date fields take words -- "tom", "next monday", "5.9" -- and that is the
quick way in when the day is already known. It is the other case this is for:
the day that is only known by where it falls, which is a question about a month
rather than about a date, and a question no line of text can be asked.

It is opened out of the field being typed into, by typing `cal` where the date
would go, so what it hands back lands in that field and nowhere else. It is
walked with the app's own direction keys: `j`/`ö` a day either way, `k`/`l` a
week, `J`/`Ö` a whole month.

Austrian, the way every date in the app is: weeks start on Monday, the day and
month names are German, and the public holidays are marked -- a day picked for
work is rarely the day everything is shut.
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

# German month names, spelled out here rather than left to `%B`, which follows
# the process locale and would give English names on a default install.
# Austrian German, so the year opens with Jänner rather than Januar
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

# What the window is titled per column: which of the two dates is being
# picked, since the field it was opened out of is behind it
COLUMN_TITLES = {
    "due": "Due date",
    "scheduled": "Scheduled date",
}


def calendar_title(column: str) -> str:
    """What a month opened over a column is titled"""

    return COLUMN_TITLES.get(column, column.capitalize())


# Monday first, which is what the weekday names are already indexed by
WEEK_START = 0

SATURDAY = 5

# How far a day is drawn towards the background when it is only there to fill
# out the week: a day of the month either side, which is shown so the weeks
# read as whole weeks rather than as rows that start and stop mid-air
OUTSIDE_FADE = 0.7

# The same, for a weekend inside the month: still a day that can be picked,
# only not one most work is planned for
WEEKEND_FADE = 0.35

# Every cell is two digits and the space either side of them
CELL_WIDTH = 4

# Weeks drawn, whatever the month asked for. A month runs to four, five or six
# of them depending on the day it opens on, and a panel sized to that would
# grow and shrink under a cursor being walked from one month into the next --
# the one moment the eye is following a single cell across the screen. The
# short months are filled out with the days either side of them rather than
# with blank rows: they are real days, drawn faded like the rest of the
# overspill, and they can be walked onto like any other.
WEEKS_DRAWN = 6


def weeks_around(day: date) -> List[List[date]]:
    """
    The fixed block of weeks a day's month is read in, Monday first

    Six whole weeks running from the Monday on or before the first of the
    month, so the block is the same shape every time and the day asked about
    is always somewhere inside it.
    """

    first = day.replace(day=1)
    start = first - timedelta(days=(first.weekday() - WEEK_START) % 7)

    return [
        [start + timedelta(days=week * 7 + weekday) for weekday in range(7)]
        for week in range(WEEKS_DRAWN)
    ]


HINT_GAP = "  "

# Only the three that are not already known. The direction keys are the same
# four the whole app is walked with, and a window that listed them would be
# teaching what the row behind it was just navigated with; these three are the
# ones this window adds. "back" rather than the "cancel" the other windows
# say: escape here drops the pick and hands the field back mid-edit, it does
# not throw the edit away.
HINT = HINT_GAP.join(("t today", "esc back", "enter pick"))

# What each key moves the cursor by. A day that runs off the end of the month
# simply lands in the next one, which is what makes a month change out of a
# day step and leaves the shifted keys to the jumps worth a key of their own.
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
    """
    The same day a number of months away, kept inside the month it lands in

    The 31st of a month before a short one has nowhere to land, so it comes
    down on the last day there is: a jump between months is about the month,
    and skidding into the one after it is not what was asked for.
    """

    month_index = day.month - 1 + months
    year = day.year + month_index // 12
    month = month_index % 12 + 1

    return date(year, month, min(day.day, monthrange(year, month)[1]))


class CalendarScreen(BaseScreen, ModalScreen):
    """
    The month the day is picked out of, over a dimmed copy of the app

    An overlay rather than a bar, for the same reason the move window is one:
    a month is a block, and a bar has one line to draw it on.
    """

    def __init__(self, title: str, initial: Optional[date] = None) -> None:
        super().__init__()

        # What the window is titled: which of the two dates is being picked.
        # Said in the border, since the field it came out of is behind it
        self._title = title

        # The day under the cursor, which is the day the window opens on: the
        # one the field already holds, or today when it holds nothing
        self._selected = initial or date.today()

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
        # Every key belongs to the window: the app's own bindings are about
        # the panes behind it, and none of them can be reached from here
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
        """
        Take a step, unless it would walk off the end of what a date can be

        The block of weeks around the day has to be drawable too, and it runs
        on past the month either way, so the last few days a date can hold are
        turned down here rather than raising out of the redraw once the cursor
        has already been moved onto one. Nobody schedules anything for the
        year 1, but a key held down long enough to get there would otherwise
        bring the app down rather than simply stop.
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
        # The blank line is what keeps the day the cursor is on from reading
        # as an eighth row of the month above it
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
        """
        The weeks of the month, Monday first, each day in its own cell

        Built as a grid rather than written out line by line, so the columns
        stay under their own headings however wide a cell has to be drawn.
        """

        # Not expanded: a grid handed more room than its columns asked for
        # shares the difference out among them, and a week is seven days wide
        # however wide the panel around it happens to be
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
        """The block of weeks the month being looked at is read in"""

        return weeks_around(self._selected)

    def _cell(self, day: date) -> Text:
        """
        One day, drawn as what it is: picked, today, a holiday, or a weekend

        The cursor is the inverted pill the app wears wherever something is
        being typed into, and it has the last word: the picked day is what the
        next keypress is about, whatever else that day happens to be.
        """

        # Two columns wide whichever day it is, and centred by the column
        # rather than by the text -- a `Text` carrying a justify of its own
        # overrides the column's. Padded so the single digits line up under
        # the tens, and so the cursor is the same pill on every day of the
        # month rather than half the width on the first nine
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

        # A day of another month is faded whatever else it is: it is only
        # drawn to fill the week out, and one that shouted would be read as
        # belonging to the month around it
        if day.month != self._selected.month:
            color = blend(color, self.theme.background2, OUTSIDE_FADE)
            bold = False

        return Style(color=color, bold=bold)

    def _footer(self) -> Group:
        """
        The day under the cursor, written out the way every date in the app is

        Two lines, always: the date, and under it the holiday the day is, if it
        is one. The red in the grid says that a day is a holiday and this is
        the only place it is named, but a name is up to nineteen letters and
        the panel is a week wide -- put beside the date it would wrap, and the
        window would gain a line on the days that have one and lose it again
        on the days that do not. So the line is kept whether or not there is
        anything to write on it.
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
