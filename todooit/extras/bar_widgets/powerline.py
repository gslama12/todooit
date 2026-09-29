from todooit.ui.api import TodooitAPI
from .text_box import TextBox
from typing_extensions import Self


class Powerline(TextBox):
    def __init__(
        self,
        api: TodooitAPI,
        text: str = "",
        fmt: str = "{}",
        fg: str = "",
        bg: str = "",
    ) -> None:
        bg = bg or api.vars.theme.background2
        super().__init__(api, text, fmt, fg, bg)

    @classmethod
    def left_rounded(cls, api: TodooitAPI, fg: str = "", bg: str = "") -> Self:
        return cls(api, "", fg=fg, bg=bg)
