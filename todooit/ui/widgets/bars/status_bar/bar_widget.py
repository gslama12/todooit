from collections.abc import Callable
from typing import Optional

from rich.style import Style
from rich.text import Text, TextType


class StatusBarWidget:
    """
    One segment of the status bar: whatever `func` last returned

    `func` is a config function decorated with `subscribe` or `timer`, and the
    config manager keeps its latest result on it. `fmt` wraps that result, and
    `fg`/`bg` paint the whole segment underneath whatever markup it carries.
    """

    def __init__(
        self,
        func: Callable[..., TextType],
        width: Optional[int] = None,
        fmt: str = "{}",
        fg: str = "",
        bg: str = "",
    ) -> None:
        self.func = func
        self.width = width
        self.fmt = fmt
        self.fg = fg
        self.bg = bg

    @property
    def value(self) -> str:
        res = getattr(self.func, "__todooit_value", "")

        if isinstance(res, Text):
            return res.markup

        return str(res)

    def render(self) -> Text:
        # A base style sits under every span, so the segment's colors fill in
        # wherever the value's own markup leaves them unset
        style = Style(color=self.fg or None, bgcolor=self.bg or None)
        return Text.from_markup(self.fmt.format(self.value), style=style)
