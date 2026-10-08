from typing import TYPE_CHECKING

from rich.console import RenderableType
from rich.style import Style
from rich.text import Text

from todooit.ui.api.events import ModeChanged

from .._base import BarBase

if TYPE_CHECKING:  # pragma: no cover
    from todooit.ui.widgets.trees.model_tree import ModelTree

# Same rounded caps the status bar's mode pill wears, since this replaces it.
CAP_LEFT = ""
CAP_RIGHT = ""

# A field edit is an insert like any other, labeled the same way the status
# bar would.
MODE_LABEL = "INSERT"


class FieldBar(BarBase):
    """
    A column being typed into, drawn where the status bar sits instead of
    inline, so making room for the buffer doesn't shift every row. The edit
    itself stays with the tree; keys are just handed straight through.
    """

    def __init__(self, tree: "ModelTree", column: str, *args, **kwargs):
        super().__init__(*args, **kwargs)
        self._tree = tree
        self.column = column

    def perform_action(self, cancel: bool) -> None:
        # Enter/escape reach the tree as keystrokes, so the edit is already
        # settled by the time this runs.
        return

    def handle_keypress(self, key: str) -> None:
        self._tree.handle_keypress(key)

        if self._tree.is_editing:
            self.refresh()
            return

        self.dismiss(cancel=False)

    def on_unmount(self):
        self.post_message(ModeChanged("NORMAL"))

        # A notification raised on the way out may have taken the bar; only
        # hand it back if it's still ours.
        if self.switcher.current == self.id:
            self.switcher.current = "status_bar"

    def render(self) -> RenderableType:
        if not self._tree.is_editing:  # pragma: no cover
            return Text()

        theme = self.api.vars.theme
        cap = Style(color=theme.secondary, bgcolor=theme.background2)

        label = Text(
            f" {MODE_LABEL} ",
            style=Style(color=theme.background1, bgcolor=theme.secondary, bold=True),
        )

        buffer = self._tree.current._get_component(self.column).render_editing(theme)

        return (
            Text(CAP_LEFT, style=cap)
            + label
            + Text(CAP_RIGHT, style=cap)
            + Text(" ")
            + buffer
        )
