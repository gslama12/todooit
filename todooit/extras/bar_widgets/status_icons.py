from rich.text import Text
from todooit.ui.api import DooitAPI, subscribe
from todooit.ui.api.events import TodoEvent, ProjectSelected
from .text_poller import Custom


def get_status_icons(completed_icon, pending_icon, overdue_icon):
    @subscribe(TodoEvent, ProjectSelected)
    def wrapper(api: DooitAPI, _):
        project = api.vars.current_project
        if not project:
            return ""

        theme = api.vars.theme

        completed = sum([i.is_completed for i in project.todos])
        pending = sum([i.is_pending for i in project.todos])
        overdue = sum([i.is_overdue for i in project.todos])

        return (
            Text()
            + Text.from_markup(completed_icon + str(completed), style=theme.green)
            + Text(" ")
            + Text.from_markup(pending_icon + str(pending), style=theme.yellow)
            + Text(" ")
            + Text.from_markup(overdue_icon + str(overdue), style=theme.red)
        )

    return wrapper


class StatusIcons(Custom):
    def __init__(
        self,
        api: DooitAPI,
        completed_icon=" ",
        pending_icon=" ",
        overdue_icon=" ",
        fmt: str = " {} ",
        bg: str = "",
    ) -> None:
        super().__init__(
            api,
            get_status_icons(completed_icon, pending_icon, overdue_icon),
            None,
            fmt,
            "",
            bg or api.vars.theme.background3,
        )
