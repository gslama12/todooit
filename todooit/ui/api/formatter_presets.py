"""
Ready-made formatters for the config to add to a column

Each call returns a fresh formatter, so the arguments (an icon, a color) are
fixed per column rather than shared.
"""

import re
from datetime import datetime
from typing import Callable, Optional
from rich.style import Style
from rich.text import Text
from todooit.api import Todo
from todooit.ui.api import TodooitAPI, extra_formatter


# An hourglass, in the same Material set the rest of the row's icons come out
# of: sand running through says the work is under way somewhere else, which is
# the whole of what the column has to report.
AGENT_ICON = "󰔟"


def agent_icon(icon: str = AGENT_ICON, color: Optional[str] = None):
    """
    The hourglass on the rows an AI has been handed, and nothing on the rest

    The flag is the whole of the column, so the icon replaces the value rather
    than leading it the way the date and recurrence icons lead theirs.
    """

    @extra_formatter
    def wrapper(value: str, model: Todo, api: TodooitAPI):
        theme = api.vars.theme

        if not model.agent:
            return value

        # Appended to an empty Text rather than handed back on its own: the
        # formatter store reads a Text back as markup, and a style sitting on
        # the whole of one is not written into that -- only a span is. The
        # append is what turns the one into the other, and what keeps the
        # color on the icon by the time the row is drawn.
        return Text() + Text.from_markup(icon, style=Style(color=color or theme.primary))

    return wrapper


def description_highlight_link(color: Optional[str] = None):
    @extra_formatter
    def wrapper(value: str, _, api: TodooitAPI):
        """
        Highlight URLs in the description.
        """

        url_pattern = re.compile(
            r"http[s]?://"
            r"(?:[a-zA-Z]|[0-9]|[$-_@.&+]|[!*\\(\\),]|"
            r"(?:%[0-9a-fA-F][0-9a-fA-F]))+",
            re.IGNORECASE,
        )

        text = Text.from_markup(value)
        text.highlight_regex(
            url_pattern,
            style=Style(
                color=color or api.vars.theme.primary,
                underline=True,
                italic=True,
            ),
        )

        return text.markup

    return wrapper


def due_danger_today(fmt: str = "{}") -> Callable:
    def wrapper(due: Optional[datetime], _: Todo, api: TodooitAPI) -> Optional[str]:
        """
        If the due date is today, show a bold red "Today" text.
        """

        if not due:
            return ""

        if due.date() == datetime.today().date():
            return Text(
                fmt.format("Today"),
                style=Style(
                    color=api.vars.theme.red,
                    bold=True,
                ),
            ).markup

        # Declined: the next formatter in the chain draws the date
        return None

    return wrapper


def recurrence_icon(icon: str = "󰑖 ", color: Optional[str] = None):
    @extra_formatter
    def wrapper(value: str, model: Todo, api: TodooitAPI):
        theme = api.vars.theme

        if not model.recurrence:
            return value

        return (
            Text()
            + Text.from_markup(icon, style=Style(color=color or theme.primary))
            + value
        )

    return wrapper
