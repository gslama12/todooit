from datetime import datetime
from todooit.ui.api import TodooitAPI, timer
from .text_poller import Custom


def get_clock_wrapper(format: str):
    @timer(1)
    def get_clock(*_) -> str:
        return datetime.now().strftime(format)

    return get_clock


class Clock(Custom):
    def __init__(
        self,
        api: TodooitAPI,
        fmt: str = " {} ",
        format: str = "%H:%M:%S",
        fg: str = "",
        bg: str = "",
    ) -> None:
        super().__init__(
            api=api,
            function=get_clock_wrapper(format),
            width=None,
            fmt=fmt,
            fg=fg,
            bg=bg,
        )
