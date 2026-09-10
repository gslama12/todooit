from typing import Callable, Optional
from rich.style import Style
from todooit.api.todo import datetime, Todo
from todooit.ui.api import DooitAPI
from rich.text import Text


def due_danger_today(fmt: str = "{}") -> Callable:
    def wrapper(due: Optional[datetime], _: Todo, api: DooitAPI) -> Optional[str]:
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

    return wrapper


