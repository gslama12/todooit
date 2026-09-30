from rich.console import RenderableType
from todooit.ui.api.events.events import NotificationType
from .._base import BarBase

# Seconds a notification stays up before giving the bar back; a key dismisses
# it sooner. Warnings and errors ask to be read, so they stay longer.
SHOWN_FOR = {"info": 3, "warning": 5, "error": 5}


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
        *args,
        **kwargs,
    ):
        super().__init__(*args, **kwargs)
        self.message = message
        self.level = level
        self.auto_exit = auto_exit
        self.focused = not auto_exit
        self.add_class(self.level)

    def perform_action(self, cancel: bool):
        return

    def on_mount(self):
        if self.auto_exit:
            self.app.set_timer(SHOWN_FOR[self.level], self.remove)

    def handle_keypress(self, key: str) -> None:
        self.remove()

    def render(self) -> RenderableType:
        return self.message
