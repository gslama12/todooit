from typing import Callable
from rich.console import RenderableType

from todooit.ui.api.events import BarNotification
from .._base import BarBase


class ConfirmBar(BarBase):
    """
    The y/N that guards an edit nothing can be undone from afterwards

    The question and both of its answers are handed in whole. A row can be
    deleted from a pane that is not the one it lives in, from a project that
    is not on screen, or out of an edit that left it nameless -- so the bar
    says which thing is about to go, and then says what became of it, rather
    than asking whether the last keypress was meant.
    """

    DEFAULT_CSS = """
    ConfirmBar {
        padding-left: 1;
        padding-right: 1;
    }
    """

    def __init__(
        self,
        callback: Callable,
        message: str,
        confirmed: str,
        cancelled: str,
        *args,
        **kwargs,
    ):
        super().__init__(callback, *args, **kwargs)
        self.message = message
        self.confirmed = confirmed
        self.cancelled = cancelled

    def perform_action(self, cancel: bool):
        if not cancel:
            self.callback()

    async def handle_keypress(self, key: str) -> None:
        cancel = key.lower() != "y"
        self.dismiss(cancel)

        if cancel:
            self.post_message(BarNotification(self.cancelled, "info"))
        else:
            self.post_message(BarNotification(self.confirmed, "warning"))

    def render(self) -> RenderableType:
        return self.message
