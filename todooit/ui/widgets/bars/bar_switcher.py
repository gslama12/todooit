from typing import Optional
from textual.await_complete import AwaitComplete
from textual.widget import Widget
from textual.widgets import ContentSwitcher
from todooit.ui.api.events.events import BarNotification, ShowConfirm
from todooit.ui.widgets.bars._base import BarBase
from .status_bar import StatusBar
from .confirm_bar import ConfirmBar
from .notification_bar import NotificationBar
from .field_bar import FieldBar


class BarSwitcher(ContentSwitcher):
    DEFAULT_CSS = """
    BarSwitcher {
        height: 1;
        width: 100%;
    }
    """

    @property
    def visible_content(self) -> BarBase:
        content = super().visible_content

        assert isinstance(content, BarBase)
        return content

    @property
    def is_focused(self):
        return self.current != "status_bar" and self.visible_content.focused

    def add_content(
        self, widget: Widget, *, id: Optional[str] = None, set_current: bool = False
    ) -> AwaitComplete:
        try:
            self.query_one(f"#{id}", expect_type=BarBase).remove()
        except Exception as _:
            pass

        return super().add_content(widget, id=id, set_current=set_current)

    def on_mount(self):
        self.status_bar = StatusBar()
        self.add_content(
            widget=self.status_bar,
            id="status_bar",
            set_current=True,
        )

    def switch_to_confirm(self, event: ShowConfirm):
        confirm_bar = ConfirmBar(
            event.callback,
            event.message,
            event.confirmed,
            event.cancelled,
        )
        self.add_content(
            widget=confirm_bar,
            id="confirm_bar",
            set_current=True,
        )

    def switch_to_field(self, tree, column: str):
        field_bar = FieldBar(tree, column)
        self.add_content(
            widget=field_bar,
            id="field_bar",
            set_current=True,
        )

    def switch_to_notification(self, event: BarNotification):
        notification_bar = NotificationBar(event.message, event.level, event.auto_exit)
        self.add_content(
            widget=notification_bar,
            id="notification_bar",
            set_current=True,
        )

    def handle_keypress(self, key: str) -> None:
        if self.current != "status_bar":
            self.visible_content.handle_keypress(key)
