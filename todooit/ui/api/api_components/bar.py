from typing import TYPE_CHECKING, List
from todooit.ui.widgets.bars import StatusBarWidget
from ._base import ApiComponent

if TYPE_CHECKING:  # pragma: no cover
    from todooit.ui.tui import DooitAPI


class BarManager(ApiComponent):
    def __init__(self, api: "DooitAPI") -> None:
        super().__init__()
        self.api = api

    def set(self, widgets: List[StatusBarWidget]):
        for widget in widgets:
            self.api.plugin_manager.register(widget.func)

        self.api.app.bar.set_widgets(widgets)
