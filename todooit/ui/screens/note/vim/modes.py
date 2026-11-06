"""
The two keyboard modes and moving between them
"""

from typing import Optional, Tuple

from textual import on
from textual.geometry import Offset
from textual.widgets import TextArea
from textual.widgets.text_area import Selection

from todooit.vim_engine import MODE_INSERT, MODE_NORMAL, FindView, VimEngine

from ..disp.markup import BACKDROP, TARGET
from ..disp.view import NoteView, Overlay
from .buffer import NoteBuffer
from .host import EditorHost

# Rows kept in view above and below the cursor, wherever the note has them
SCROLLOFF = 4


class ModalEditor(NoteView):
    """
    The note as a host of the vim engine, which decides the mode.
    `read_only` is what NORMAL *is*.
    """

    def __init__(self, text: str) -> None:
        # Always opens in NORMAL. tab_behavior stays "focus" so escape bubbles.
        super().__init__(text, read_only=True)

        # Built on first use, once there's an app to read the keymap from
        self._engine: Optional[VimEngine] = None

        # The character jump being shown
        self._find_view: Optional[FindView] = None

    @property
    def host(self) -> EditorHost:
        """The window this editor is in."""

        screen = self.screen

        assert isinstance(screen, EditorHost)
        return screen

    @property
    def engine(self) -> VimEngine:
        if self._engine is None:
            self._engine = VimEngine(NoteBuffer(self), self.app.api.vim.keys)

        return self._engine

    @property
    def mode(self) -> str:
        return MODE_NORMAL if self.read_only else MODE_INSERT

    def enter_insert(self) -> None:
        self.engine.set_mode(MODE_INSERT)

    def enter_normal(self) -> None:
        self.engine.set_mode(MODE_NORMAL)

    def show_mode(self, mode: str) -> None:
        """Take on the mode the engine has just moved to."""

        self.read_only = mode == MODE_NORMAL
        self.host.mode_changed()

    def half_page(self) -> int:
        """
        Half the window height, never less than a line, so scroll distance matches the terminal size.
        """

        return max(1, self.content_size.height // 2)

    @property
    def cursor_y(self) -> int:
        """How far down the drawn note the cursor's row is."""

        return self.wrapped_document.location_to_offset(self.cursor_location).y

    def rows_with_context(self, top: int) -> Tuple[int, int]:
        """
        The first and last rows down the drawn note the cursor may stand on, with
        the view's top at `top`. A window too short for the context leaves the
        middle, and the note's own ends need none.
        """

        height = self.content_size.height
        margin = min(SCROLLOFF, (height - 1) // 2)

        return (
            top + margin if top > 0 else 0,
            top + height - 1 - (margin if top < self.max_scroll_y else 0),
        )

    def scroll_cursor_visible(
        self, center: bool = False, animate: bool = False
    ) -> Offset:
        """
        Everything that moves the cursor ends up here. Upstream only brings it on
        screen, and later, so a key's effect can't be built on; this scrolls now.
        """

        height = self.content_size.height

        if not self._has_cursor or height < 1:
            return Offset(0, 0)

        self._recompute_cursor_offset()

        y = self.cursor_y
        before = top = self.scroll_offset.y

        if center:
            top = y - (height - 1) // 2
        else:
            first, last = self.rows_with_context(top)
            top += min(0, y - first) + max(0, y - last)

        top = max(0, min(top, self.max_scroll_y))
        self.scroll_to(y=top, animate=False, immediate=True)

        return Offset(0, top - before)

    def show_find_view(self) -> None:
        """Dim the text a character jump looks across, and light up where it can go."""

        view = self.engine.find_view

        if view != self._find_view:
            self._find_view = view
            self.show_overlay(self._find_overlay(view) if view else None)

    @on(TextArea.SelectionChanged)
    def _cursor_moved(self) -> None:
        """A click moves the cursor with no key for the engine to see."""

        self.show_find_view()

    def _find_overlay(self, view: FindView) -> Overlay:
        row, column = view.origin
        rows = range(self.document.line_count)
        spans = [(*place, place[1] + 1, TARGET) for place in view.targets]

        if view.forward is None:
            return Overlay(rows, spans)

        if view.forward:
            end = len(self._stored_line(row))
            dim = (row, column + 1, end, BACKDROP)
            return Overlay(rows[row + 1 :], [dim, *spans])

        return Overlay(rows[:row], [(row, 0, column, BACKDROP), *spans])

    def _validate_selection(self, selection: Selection) -> Selection:
        """
        In NORMAL the cursor stands on a character, however it got there: a
        click, a page key, a search result. A selection may run past the last
        one, to take the line's end with it.
        """

        selection = super()._validate_selection(selection)

        if not self.read_only or not selection.is_empty:
            return selection

        row, column = selection.end
        last = max(0, len(self._stored_line(row)) - 1)

        return Selection.cursor((row, last)) if column > last else selection
