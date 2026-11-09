from datetime import date, datetime, time
from typing import Any, Optional

from rich.style import Style
from rich.text import Text

from todooit.api import Cadence, Project, Todo, lifecycle
from todooit.api.lifecycle import Outcome
from todooit.api.theme import TodooitThemeBase
from todooit.utils import parse

from .simple_input import SimpleInput
from .vim_input import VimDescription

# Typed into a date field, opens the calendar instead of being parsed as a
# date (no date expression starts with "cal"). A plain word rather than a
# bound key, since modified keys aren't reliable in a terminal.
CALENDAR_WORD = "cal"


class TodoDescription(VimDescription[Todo]):
    @property
    def _property(self) -> str:
        return "description"


class ProjectDescription(VimDescription[Project]):
    @property
    def _property(self) -> str:
        return "description"


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
        """Whether the typed text is a request to open the calendar."""

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


class Status(SimpleInput[Todo, str]):
    def _get_default_value(self) -> str:
        val = self.model_value

        if val == "completed":
            return "x"

        if val == "overdue":
            return "!"

        return "o"

    def _typecast_value(self, value: str) -> Any:
        return value != "COMPLETED"


class Recurrence(SimpleInput[Todo, Cadence]):
    def _typecast_value(self, value: str) -> Optional[Cadence]:
        if not value:
            return None

        return Cadence.parse(value)

    def _write(self, value: Optional[Cadence]) -> Outcome:
        return lifecycle.set_recurrence(self.model, value)

    def _get_default_value(self) -> str:
        value = self.model_value

        if value is None:
            return ""

        return str(value)
