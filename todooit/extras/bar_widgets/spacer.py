from todooit.ui.api import TodooitAPI
from ._base import BarUtilWidgetBase


class Spacer(BarUtilWidgetBase):
    def __init__(self, api: TodooitAPI, width: int, fg: str = "", bg: str = "") -> None:
        super().__init__(func=lambda *_: "", width=width, api=api, fg=fg, bg=bg)
