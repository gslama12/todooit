from typing import TYPE_CHECKING, Callable

from textual.widgets import Static

from ...api.events import ModeChanged

if TYPE_CHECKING:  # pragma: no cover
    from todooit.ui.api.todooit_api import TodooitAPI
    from todooit.ui.tui import Todooit

    from .bar_switcher import BarSwitcher


class BarBase(Static):
    DEFAULT_CSS = """
    BarBase {
        height: 1;
        width: 100%;
    }
    """

    focused: bool = True

    def __init__(self, callback: Callable = lambda: None, *args, **kwargs):
        super().__init__(*args, **kwargs)
        self.callback = callback

    @property
    def app(self) -> "Todooit":
        from todooit.ui.tui import Todooit

        app = super().app
        assert isinstance(app, Todooit)
        return app

    @property
    def api(self) -> "TodooitAPI":  # pragma: no cover
        return self.app.api

    @property
    def switcher(self) -> "BarSwitcher":
        from .bar_switcher import BarSwitcher

        parent = self.parent
        assert isinstance(parent, BarSwitcher)
        return parent

    def on_unmount(self):
        self.post_message(ModeChanged("NORMAL"))
        self.switcher.current = "status_bar"

    def perform_action(self, cancel: bool):
        raise NotImplementedError  # pragma: no cover

    def dismiss(self, cancel: bool):
        self.perform_action(cancel)
        self.app.post_message(ModeChanged("NORMAL"))
        self.remove()

    def handle_keypress(self, key: str) -> None:  # pragma: no cover
        return
