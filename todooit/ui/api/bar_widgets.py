"""
Ready-made status bar widgets for the config to hand to `api.bar.set`

Each one is a plain `StatusBarWidget` around a function that says when its
value changes: once at startup, on a timer, or on an event.
"""

from datetime import datetime
from typing import Optional, Union
from rich.text import TextType
from todooit.ui.api import TodooitAPI, subscribe, timer
from todooit.ui.api.events import ProjectSelected, Startup
from todooit.ui.widgets.bars import StatusBarWidget


def text(
    content: TextType,
    fmt: str = "{}",
    fg: str = "",
    bg: str = "",
    width: Optional[int] = None,
) -> StatusBarWidget:
    """Fixed text, such as a powerline cap"""

    @subscribe(Startup)
    def value(*_) -> TextType:
        return content

    return StatusBarWidget(value, width, fmt, fg, bg)


def spacer(width: int = 0, fg: str = "", bg: str = "") -> StatusBarWidget:
    """Empty room; a width of 0 takes whatever the other widgets leave over"""

    return StatusBarWidget(lambda *_: "", width, fg=fg, bg=bg)


def clock(
    format: str = "%H:%M:%S",
    fmt: str = " {} ",
    fg: str = "",
    bg: str = "",
) -> StatusBarWidget:
    """The time of day, read once a second"""

    @timer(1)
    def now(*_) -> str:
        return datetime.now().strftime(format)

    return StatusBarWidget(now, fmt=fmt, fg=fg, bg=bg)


def current_project(
    no_project_text: str = "No Project Selected",
    fmt: str = " {} ",
    fg: str = "",
    bg: str = "",
) -> StatusBarWidget:
    """The selected project, prefixed with its parent when it has one"""

    @subscribe(ProjectSelected, Startup)
    def name(_: TodooitAPI, event: Union[ProjectSelected, Startup]) -> str:
        if isinstance(event, Startup):
            return no_project_text

        text = event.project.description
        parent = event.project.parent_project

        if parent and not parent.is_root:
            text = f"{parent.description}/{text}"

        return text

    return StatusBarWidget(name, fmt=fmt, fg=fg, bg=bg)
