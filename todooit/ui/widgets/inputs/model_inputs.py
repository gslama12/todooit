import re
from datetime import date, datetime, time, timedelta
from typing import Any, Optional, Tuple

from rich.style import Style
from rich.text import Text

from .simple_input import SimpleInput
from todooit.api import Todo, Project, lifecycle
from todooit.api.lifecycle import Outcome
from todooit.api.theme import TodooitThemeBase
from todooit.utils import parse

# Typed into a date field, opens the calendar instead of being parsed as a
# date (no date expression starts with "cal"). A plain word rather than a
# bound key, since modified keys aren't reliable in a terminal.
CALENDAR_WORD = "cal"


class TodoDescription(SimpleInput[Todo, str]):
    @property
    def _property(self) -> str:
        return "description"


class ProjectDescription(SimpleInput[Project, str]):
    @property
    def _property(self) -> str:
        return "description"


class ProjectTasks(SimpleInput[Project, int]):
    """How many todos are nested under the project; derived, so never editable."""

    editable = False

    @property
    def _property(self) -> str:
        return "total_todos"

    @property
    def value(self) -> str:
        # Recounted each render since todos come and go.
        count = self.model_value

        if not count:
            return ""

        return str(count)


class Note(SimpleInput[Todo, str]):
    """
    The free text hanging off a todo, edited in its own window, never inline.
    Column is read-only with an empty buffer: `_get_attr_width` measures the
    buffer, and a real note would stretch the column to its longest line.
    """

    editable = False

    def _get_default_value(self) -> str:
        return ""


class DateInput(SimpleInput[Todo, datetime]):
    """A column holding a single date: the deadline, or the day planned for it."""

    # Day-first, to match the column's rendering and how the parser reads an ambiguous "5.9".
    EDIT_FORMAT = "%d.%m.%Y"

    def asks_for_calendar(self) -> bool:
        return self.value.strip().lower() == CALENDAR_WORD

    def take_back_word(self) -> None:
        """Restore the field to how it was before "cal" was typed, so escaping the calendar doesn't leave it behind."""

        self.start_edit()

    def _parsed(self) -> Optional[datetime]:
        """What is in the buffer right now, as a date, or None if it is not one"""

        typed = self.value.strip()

        if not typed:
            return None

        parsed, ok = parse(typed)

        return parsed if ok else None

    def calendar_day(self) -> Optional[date]:
        """Day the calendar opens on: the half-typed buffer wins over the model's value."""

        parsed = self._parsed()

        return parsed.date() if parsed else None

    def set_day(self, day: date) -> None:
        """Write a day picked off the calendar into the buffer, keeping any time already typed."""

        parsed = self._parsed()
        clock = parsed.time() if parsed else time()

        self._value = self._format(datetime.combine(day, clock))
        self._selection_anchor = None
        self.move_cursor_to_end()

    @classmethod
    def _format(cls, value: datetime) -> str:
        dt_format = cls.EDIT_FORMAT

        if value.hour or value.minute:
            dt_format += " %H:%M"

        return value.strftime(dt_format)

    def _get_default_value(self) -> str:
        value = self.model_value

        if value is None:
            return ""

        return self._format(value)

    def _typecast_value(self, value: str) -> Any:
        if not value.strip():
            return None

        date, ok = parse(value)
        if not ok:
            # Raised, not swallowed, so the tree turns it into a notification.
            raise ValueError(f'Could not understand {self._property} date: "{value}"')

        return date

    def render_editing(self, theme: TodooitThemeBase) -> Text:
        """The buffer, plus what the text currently in it resolves to."""

        text = super().render_editing(theme)

        if not self.value.strip():
            return text

        date, ok = parse(self.value)

        if not ok:
            hint, color = "?", theme.red
        elif date is None:
            hint, color = "no date", theme.green
        else:
            hint, color = self._format(date), theme.green

        return text + Text(f" → {hint}", style=Style(color=color, dim=True))


class Due(DateInput):
    """
    The date the todo has to be done by
    """

    def _write(self, value: Optional[datetime]) -> Outcome:
        return lifecycle.set_due(self.model, value)


class Scheduled(DateInput):
    """
    The date the todo is planned to be worked on
    """

    def _write(self, value: Optional[datetime]) -> Outcome:
        return lifecycle.schedule(self.model, value)


class Completed(DateInput):
    """The date the todo was ticked off; set by the app, not typed."""

    editable = False

    @property
    def _property(self) -> str:
        return "completed_at"


class Binned(DateInput):
    """The date the todo was thrown away; set by the app, not typed."""

    editable = False

    @property
    def _property(self) -> str:
        return "binned_at"


class Priority(SimpleInput[Todo, int]):
    @property
    def value(self) -> str:
        res = self.model.priority

        if res == 0:
            return ""

        return str(self.model.priority)

    def _typecast_value(self, value: str) -> Any:
        if not value or value == "0":
            return 0

        return int(value)


class Agent(SimpleInput[Todo, bool]):
    """
    Whether an AI has been handed the todo. A toggled flag, never typed into,
    so the column is read-only with an empty buffer (like Note).
    """

    editable = False

    def _get_default_value(self) -> str:
        return ""


class Status(SimpleInput[Todo, str]):
    def _get_default_value(self) -> str:
        val = self.model_value

        if val == "completed":
            return "x"

        if val == "overdue":
            return "!"

        return "o"

    def _typecast_value(self, value: str) -> Any:
        if value == "COMPLETED":
            return False

        return True


class Recurrence(SimpleInput[Todo, timedelta]):
    @staticmethod
    def parse_recurrence(recurrence: str) -> timedelta:
        DURATION_LEGEND = {
            "m": "minute",
            "h": "hour",
            "d": "day",
            "w": "week",
        }

        def split_duration(duration: str) -> Tuple[str, str]:
            if re.match(r"^(\d+)[mhdw]$", duration):
                return duration[-1], duration[:-1]
            else:
                raise ValueError("Invalid recurrence format")

        sign, frequency = split_duration(recurrence)
        frequency = int(frequency)
        return timedelta(**{f"{DURATION_LEGEND[sign]}s": frequency})

    def _typecast_value(self, value: str) -> Optional[timedelta]:
        if not value:
            return None

        return self.parse_recurrence(value)

    def _write(self, value: Optional[timedelta]) -> Outcome:
        return lifecycle.set_recurrence(self.model, value)

    @staticmethod
    def timedelta_to_simple_string(td: timedelta):
        if td.days >= 7 and td.days % 7 == 0:
            weeks = td.days // 7
            return f"{weeks}w"
        elif td.days > 0:
            return f"{td.days}d"
        elif td.seconds >= 3600:
            hours = td.seconds // 3600
            return f"{hours}h"
        elif td.seconds >= 60:
            minutes = td.seconds // 60
            return f"{minutes}m"

        return "?"

    def _get_default_value(self) -> str:
        value = self.model_value

        if value is None:
            return ""

        return self.timedelta_to_simple_string(value)
