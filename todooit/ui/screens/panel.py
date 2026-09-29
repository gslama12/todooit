"""
Shared base for the one-line windows laid over the app (quick add, move, find)
"""

from rich.style import Style
from rich.text import Text
from textual import events
from textual.app import ComposeResult
from textual.screen import ModalScreen
from textual.widgets import Static

from todooit.api.theme import TodooitThemeBase
from todooit.ui.widgets.inputs._input import Input
from todooit.utils import blend

from .base import BaseScreen

# The glyph every line typed over the app starts with
PROMPT = "❯ "

# Separates the entries of a key hint
HINT_GAP = "  "

# The glyphs the panes draw projects and dates with, so a window names them
# the same way
PROJECT_ICON = "󰉋"
DATE_ICON = "󰃰"

# How far secondary text (implied values, empty states) fades to the background
FADE = 0.45


class PanelScreen(BaseScreen, ModalScreen):
    """
    A bordered panel with a one-line input and a key hint under it

    Subclasses set `PANEL_TITLE` and `HINT`, handle keys in `line_key`,
    draw the panel in `_redraw` and may load data in `_opened`.
    """

    PANEL_TITLE = ""
    HINT = ""

    def __init__(self) -> None:
        super().__init__()

        self._input = Input()
        self._input.is_editing = True

        # The last complaint about the line, shown until the next keystroke
        self._warning = ""

    @property
    def theme(self) -> TodooitThemeBase:
        return self.api.vars.theme

    @property
    def panel(self) -> Static:
        return self.query_one("#panel", Static)

    @property
    def hint(self) -> Static:
        return self.query_one("#hint", Static)

    def compose(self) -> ComposeResult:
        yield Static(id="panel")
        yield Static(self.HINT, id="hint")

    def on_mount(self) -> None:
        self.panel.border_title = self.PANEL_TITLE
        self._opened()
        self._redraw()

    async def handle_key(self, event: events.Key) -> bool:
        # Every key belongs to the line, even ones the app binds elsewhere
        event.stop()
        self.line_key(self.resolve_key(event))
        return True

    # ------------------------------------------------------------------
    # Hooks
    # ------------------------------------------------------------------

    def _opened(self) -> None:
        """Runs once on mount, before the first draw"""

    def line_key(self, key: str) -> None:
        raise NotImplementedError  # pragma: no cover

    def _redraw(self) -> None:
        raise NotImplementedError  # pragma: no cover

    # ------------------------------------------------------------------
    # Drawing helpers
    # ------------------------------------------------------------------

    def _line(self) -> Text:
        # Drawn by the buffer itself so a selection in it is highlighted
        buffer = self._input.render_editing(self.theme)
        buffer.style = Style(color=self.theme.foreground3)

        return Text(PROMPT, style=Style(color=self.theme.primary, bold=True)) + buffer

    def _faded_color(self) -> str:
        return blend(self.theme.foreground1, self.theme.background2, FADE)

    def _faded(self, message: str) -> Text:
        return Text(message, style=Style(color=self._faded_color()))

    def _warning_text(self) -> Text:
        return Text(self._warning, style=Style(color=self.theme.red, bold=True))

    def _reject(self, warning: str) -> None:
        self._warning = warning
        self._redraw()
