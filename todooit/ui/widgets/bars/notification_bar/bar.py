from typing import Optional

from rich.console import RenderableType
from rich.errors import MarkupError
from rich.table import Table
from rich.text import Text
from textual import events

from todooit.ui.api.events.events import NotificationType
from todooit.utils.clipboard import copy_text

from .._base import BarBase

# Seconds a notification stays up before giving the bar back; a key dismisses
# it sooner. Warnings and errors ask to be read, so they stay longer - errors
# longest, since they can be clicked to copy and the hand has to find the mouse.
SHOWN_FOR = {"info": 3, "warning": 5, "error": 10}

# Shown at the right edge of an error: a click anywhere on the bar copies it
COPY_LABEL = "⧉ Copy"

# What a copied error turns into, and for how long before it gives the bar back
COPIED = "Error copied to clipboard"
COPIED_SHOWN_FOR = 2


def as_text(message: str) -> Text:
    """
    The message with its markup applied - or as typed, if it is not valid
    markup (an exception's text can hold brackets of its own)
    """

    try:
        return Text.from_markup(message)
    except MarkupError:
        return Text(message)


class NotificationBar(BarBase):
    DEFAULT_CSS = """
    NotificationBar {
        padding-left: 1;
        padding-right: 1;
    }
    """

    def __init__(
        self,
        message: str,
        level: NotificationType = "info",
        auto_exit: bool = True,
        details: Optional[str] = None,
        *args,
        **kwargs,
    ):
        super().__init__(*args, **kwargs)
        self.message = message
        self.level = level
        self.auto_exit = auto_exit
        self.details = details
        self.focused = not auto_exit
        self.add_class(self.level)

    @property
    def copyable(self) -> bool:
        return self.level == "error"

    @property
    def clipboard_text(self) -> str:
        """What a click puts on the clipboard: the message as read, then any details"""

        text = as_text(self.message).plain
        if self.details:
            text = f"{text}\n\n{self.details.rstrip()}"

        return text

    def perform_action(self, cancel: bool):
        return

    def on_mount(self):
        self.timer = None
        if self.auto_exit:
            self.timer = self.app.set_timer(SHOWN_FOR[self.level], self.remove)

    def on_click(self, event: events.Click) -> None:
        if not self.copyable:
            return

        event.stop()
        copy_text(self.app, self.clipboard_text)

        # Turned into the confirmation in place, rather than swapped for a
        # new bar, so the bar never blinks back to the status line in between
        if self.timer is not None:
            self.timer.stop()
        self.remove_class(self.level)
        self.level, self.message, self.details = "info", COPIED, None
        self.add_class(self.level)
        self.timer = self.app.set_timer(COPIED_SHOWN_FOR, self.remove)
        self.refresh()

    def handle_keypress(self, key: str) -> None:
        self.remove()

    def render(self) -> RenderableType:
        if not self.copyable:
            return self.message

        grid = Table.grid(expand=True)
        grid.add_column(ratio=1, no_wrap=True, overflow="ellipsis")
        grid.add_column(justify="right", no_wrap=True)
        grid.add_row(as_text(self.message), f"  {COPY_LABEL}")
        return grid
