from typing import Callable

from rich.console import RenderableType

from todooit.ui.api.events import BarNotification

from .._base import BarBase


class ConfirmBar(BarBase):
    """
    The y/N that guards an irreversible edit. Question and both answer
    messages are passed in whole, since the bar needs to name the specific
    thing about to go (which may not be visible or even in the current pane).
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

    def handle_keypress(self, key: str) -> None:
        cancel = key.lower() != "y"
        self.dismiss(cancel)

        if cancel:
            self.post_message(BarNotification(self.cancelled, "info"))
        else:
            self.post_message(BarNotification(self.confirmed, "warning"))

    def render(self) -> RenderableType:
        return self.message
