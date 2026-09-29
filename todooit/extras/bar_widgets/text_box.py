from todooit.ui.api import TodooitAPI, subscribe, events
from rich.text import TextType
from ._base import BarUtilWidgetBase


def text_wrapper(text: TextType):
    @subscribe(events.Startup)
    def wrapper(*_):
        return text

    return wrapper


class TextBox(BarUtilWidgetBase):
    def __init__(
        self,
        api: TodooitAPI,
        text: TextType,
        fmt: str = "{}",
        fg: str = "",
        bg: str = "",
    ) -> None:
        super().__init__(
            func=text_wrapper(text), width=None, api=api, fmt=fmt, fg=fg, bg=bg
        )
