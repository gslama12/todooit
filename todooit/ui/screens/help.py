from typing import List, Tuple
from rich.console import Group, RenderableType
from rich.rule import Rule
from rich.table import Table
from rich.text import Text
from textual.app import ComposeResult, events

from todooit.ui.api.api_components.keys import KeyManager
from .base import BaseScreen
from textual.widgets import Static


class DooitKeyTable(Static):
    DEFAULT_CSS = """
    DooitKeyTable {
        content-align: center middle;
        width: 80%;
        margin: 1;
        padding: 1 2;
    }
    """

    COMPONENT_CLASSES = {
        "keybind",
        "arrow",
        "description",
        "table-title",
        "separator",
    }
    BORDER_TITLE = "Key Bindings"

    def __init__(self, keybinds: KeyManager):
        super().__init__()
        self.keybinds = keybinds

    # Keys that arrive as a character nobody can see, and so have to be named
    KEY_LABELS = {" ": "space"}

    def _rows(self, group: str) -> List[Tuple[str, str]]:
        """
        The rows a section lists, as the key it names and what it does

        A binding carrying a label of its own is written under that instead of
        under its key, and the whole run of bindings sharing one collapses to
        the single row they all read as: a scale is one thing to learn, and
        four rows of it is four times the screen saying so.
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

        # A named key is written `<ctrl+q>` so that it can be told apart from
        # the four characters it would otherwise be, which is a distinction
        # only the key input cares about: the table reads it as a key
        if keybind.startswith("<") and keybind.endswith(">"):
            return keybind[1:-1]

        return keybind

    def _render_group(self, group: str, key_width: int) -> RenderableType:
        t = Table.grid(expand=True, padding=(0, 1))
        # A fixed key column keeps the arrows lined up across every section;
        # the description soaks up whatever width is left over
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
            # A blank line above the rule and the section title straight under
            # it. The gap the sections were once given on either side is worth
            # less than the whole listing being on screen at once: a screen of
            # blank lines is what pushes the last section off the bottom of it.
            if renderables:
                renderables += [Text(""), separator]

            if group:
                title = Text(group, style=self.get_component_rich_style("table-title"))
                title.pad(1)
                renderables.append(title)

            renderables.append(self._render_group(group, key_width))

        return Group(*renderables)


class HelpScreen(BaseScreen):
    """
    Help Screen to view Help Menu
    """

    DEFAULT_CSS = """
    HelpScreen {
        align: center top;
    }
    """

    BINDINGS = [
        ("escape", "app.pop_screen", "Pop screen"),
    ]

    # The listing is taller than the screen on anything but a big terminal, so
    # it moves under the same navigation cluster as everything else: `k`/`l`
    # up and down, `j`/`ö` left and right, with the arrows alongside them
    SCROLLS = {
        "k": "scroll_up",
        "l": "scroll_down",
        "j": "scroll_left",
        "ö": "scroll_right",
        "up": "scroll_up",
        "down": "scroll_down",
        "left": "scroll_left",
        "right": "scroll_right",
        "G": "scroll_end",
    }

    # Raised by the first `g` of a `gg` and by nothing else
    _pending_g = False

    def compose(self) -> ComposeResult:
        yield DooitKeyTable(self.api.keys)

    def on_screen_resume(self) -> None:
        self._pending_g = False

    def on_key(self, event: events.Key) -> None:
        key = self.resolve_key(event)

        # Only the key straight after a `g` can be its second half, so the
        # flag is read and dropped in one go
        pending_g, self._pending_g = self._pending_g, False

        if key == "g":
            if pending_g:
                self.scroll_home()
            else:
                self._pending_g = True

            event.stop()
            return

        if scroll := self.SCROLLS.get(key):
            getattr(self, scroll)()
            event.stop()
