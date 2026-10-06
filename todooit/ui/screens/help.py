from typing import Dict, List, Tuple
from rich.console import Group, RenderableType
from rich.rule import Rule
from rich.table import Table
from rich.text import Text
from textual.app import ComposeResult, events
from textual.containers import VerticalScroll
from textual.screen import ModalScreen
from textual.widgets import Static

from todooit.ui.api.api_components.keys import KeyManager
from .base import BaseScreen
from .panel import HINT_GAP


class TodooitKeyTable(Static):
    DEFAULT_CSS = """
    TodooitKeyTable {
        width: 1fr;
        height: auto;
        padding: 0 1;
    }
    """

    COMPONENT_CLASSES = {
        "keybind",
        "arrow",
        "description",
        "table-title",
        "separator",
    }
    def __init__(self, keybinds: KeyManager):
        super().__init__()
        self.keybinds = keybinds

    # Keys with no visible character need an explicit name
    KEY_LABELS = {" ": "space"}

    def _rows(self, group: str) -> List[Tuple[str, str]]:
        """Rows for a section: (key or label, description).

        Bindings sharing a label collapse into one row instead of repeating it.
        """

        rows: List[Tuple[str, str]] = []

        for keybind, func in self.keybinds.get_keybinds_by_group(group):
            if func.description == "<NOP>":
                continue

            row = (func.label or self.key_label(keybind), func.description)

            if row not in rows:
                rows.append(row)

        return rows

    @classmethod
    def key_label(cls, keybind: str) -> str:
        if keybind in cls.KEY_LABELS:
            return cls.KEY_LABELS[keybind]

        # Strip the `<...>` markup used to distinguish a named key from literal characters
        if keybind.startswith("<") and keybind.endswith(">"):
            return keybind[1:-1]

        return keybind

    def _render_group(self, group: str, key_width: int) -> RenderableType:
        t = Table.grid(expand=True, padding=(0, 1))
        # Fixed key column keeps arrows aligned across sections; description fills the rest
        t.add_column("key", width=key_width)
        t.add_column("arrow", width=2)
        t.add_column("description", ratio=1)

        for label, description in self._rows(group):
            t.add_row(
                Text(label, style=self.get_component_rich_style("keybind")),
                Text("->", style=self.get_component_rich_style("arrow")),
                Text(
                    description,
                    style=self.get_component_rich_style("description"),
                ),
            )

        return t

    def render(self) -> RenderableType:
        separator = Rule(
            characters="─",
            style=self.get_component_rich_style("separator"),
        )

        key_width = max(
            (
                len(label)
                for group in self.keybinds.groups
                for label, _ in self._rows(group)
            ),
            default=0,
        )

        renderables = []

        for group in self.keybinds.groups:
            # Kept tight (blank line + rule, no gap below) so the whole listing fits on screen
            if renderables:
                renderables += [Text(""), separator]

            if group:
                title = Text(group, style=self.get_component_rich_style("table-title"))
                title.pad(1)
                renderables.append(title)

            renderables.append(self._render_group(group, key_width))

        return Group(*renderables)


# Panel border title
PANEL_TITLE = "Key Bindings"


# Hint bar: just navigation/exit, not the keybind listing itself
def hint(up: str, down: str) -> str:
    return HINT_GAP.join((f"{up}/{down} scroll", "gg/G top/end", "esc close"))


class HelpScreen(BaseScreen, ModalScreen):
    """Key bindings panel over a dimmed app; spawned fresh, not kept as a named screen."""

    # Listing usually overflows the panel, so it scrolls: the panes' direction
    # keys (see `scrolls`) and the arrows
    SCROLLS = {
        "up": "scroll_up",
        "down": "scroll_down",
        "left": "scroll_left",
        "right": "scroll_right",
        "G": "scroll_end",
    }

    # Raised by the first `g` of a `gg` and by nothing else
    _pending_g = False

    @property
    def panel(self) -> VerticalScroll:
        return self.query_one("#help-panel", VerticalScroll)

    def compose(self) -> ComposeResult:
        # can_focus=False: a focused scroll view has its own arrow bindings, which would steal keys from the screen
        with VerticalScroll(id="help-panel", can_focus=False):
            yield TodooitKeyTable(self.api.keys)

        motions = self.api.motion_keys()
        yield Static(hint(motions.up, motions.down), id="help-hint")

    def on_mount(self) -> None:
        self.panel.border_title = PANEL_TITLE

    def scrolls(self) -> Dict[str, str]:
        motions = self.api.motion_keys()

        return {
            **self.SCROLLS,
            motions.up: "scroll_up",
            motions.down: "scroll_down",
            motions.left: "scroll_left",
            motions.right: "scroll_right",
        }

    async def handle_key(self, event: events.Key) -> bool:
        # Modal owns every key; the app's bindings are for the panes behind it
        event.stop()

        key = self.resolve_key(event)

        if key == "escape":
            self.dismiss()
            return True

        # Only the key immediately after a `g` can complete `gg`
        pending_g, self._pending_g = self._pending_g, False

        if key == "g":
            if pending_g:
                self.panel.scroll_home()
            else:
                self._pending_g = True

        elif scroll := self.scrolls().get(key):
            getattr(self.panel, scroll)()

        return True
