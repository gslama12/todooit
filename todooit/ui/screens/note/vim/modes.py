"""
The two keyboard modes and moving between them
"""

from typing import Optional, Sequence, Tuple

from textual import on
from textual.document._edit import Edit
from textual.geometry import Offset
from textual.timer import Timer
from textual.widgets import TextArea
from textual.widgets.text_area import Selection

from todooit.ui.slim_cursor import slim_cursor
from todooit.vim_engine import (
    MODE_INSERT,
    MODE_NORMAL,
    MODE_VISUAL,
    MODE_VISUAL_LINE,
    VISUAL_MODES,
    FindView,
    Search,
    VimEngine,
    VimFlashMatch,
    VimFlashView,
    YankedRange,
)

from ..disp.document import FoldedDocument
from ..disp.markup import (
    BACKDROP,
    MARKED,
    MARKED_FIRST,
    SEARCH_MATCH,
    SELECTED,
    TARGET,
    YANKED,
)
from ..disp.view import NoteView, Overlay, OverlaySpan
from .buffer import NoteBuffer
from .history import NoteHistory, UndoStep
from .host import EditorHost

__all__ = [
    "MODE_INSERT",
    "MODE_NORMAL",
    "MODE_VISUAL",
    "MODE_VISUAL_LINE",
    "VISUAL_MODES",
    "ModalEditor",
]

# Rows kept in view above and below the cursor, wherever the note has them
SCROLLOFF = 4

# How long what was just yanked stays lit, as LazyVim's `vim.hl.on_yank()`
YANK_FLASH = 0.15


class ModalEditor(NoteView):
    """
    The note as a host of the vim engine, which decides the mode.
    `read_only` is what NORMAL *is*, and VISUAL too: its selection is the
    TextArea's, so it draws raw and the clipboard keys take it.
    """

    # Built on first use, once there's an app to read the keymap from. Up here
    # since drawing, which asks after it, starts before `__init__` is through.
    _engine: Optional[VimEngine] = None

    # The search whose matches are drawn
    _shown_search: Optional[Search] = None

    def __init__(self, text: str) -> None:
        # Always opens in NORMAL. tab_behavior stays "focus" so escape bubbles.
        super().__init__(text, read_only=True)

        self.history: NoteHistory = NoteHistory()

        # The character jump being shown
        self._find_view: Optional[FindView] = None

        # The vim_flash being shown
        self._vim_flash_view: Optional[VimFlashView] = None

        # The selection VISUAL last drew, and V-LINE's rows if it's that
        self._visual_selection: Optional[Selection] = None
        self._selected_rows: Optional[range] = None

        # Whether the mouse, not a key, last had a hand in the selection
        self.mouse_selecting = False

        # What a yank just took, lit until the timer or the next key
        self._yank_spans: Sequence[OverlaySpan] = ()
        self._yank_timer: Optional[Timer] = None

    @property
    def host(self) -> EditorHost:
        """The window this editor is in."""

        screen = self.screen

        assert isinstance(screen, EditorHost)
        return screen

    @property
    def engine(self) -> VimEngine:
        if self._engine is None:
            api = self.app.api
            self._engine = VimEngine(
                NoteBuffer(self),
                api.vim.keys,
                search_memory=api.vim.search,
                register_memory=api.vim.register,
                vim_flash_alphabet=api.vars.vim_flash_alphabet,
            )

        return self._engine

    @property
    def mode(self) -> str:
        return self.engine.mode

    @property
    def search_prompt(self) -> Optional[str]:
        """What's typed in the search prompt, or None if it isn't open."""

        return self.engine.search_prompt

    def enter_insert(self) -> None:
        self.engine.set_mode(MODE_INSERT)

    def enter_normal(self) -> None:
        self.engine.set_mode(MODE_NORMAL)

    def show_mode(self, mode: str) -> None:
        """Take on the mode the engine has just moved to."""

        self.read_only = mode != MODE_INSERT
        self._show_slim_cursor()

        if mode not in VISUAL_MODES:
            self._visual_selection = None

            if self._selected_rows is not None:
                self._selected_rows = None
                self.show_overlay(self.overlay)

        self.host.mode_changed()

    @property
    def _draw_cursor(self) -> bool:
        # INSERT's cursor is the terminal's own, slim, between characters
        return self.read_only and super()._draw_cursor

    def _show_slim_cursor(self) -> None:
        """The terminal's cursor, for INSERT, while this has the keyboard."""

        cursor = slim_cursor(self.app)
        block = self._theme.cursor_style if self._theme else None

        if self.has_focus and not self.read_only:
            # The block's own color, so the cursor looks the same in both modes
            if block is not None and block.bgcolor is not None:
                cursor.show(block.bgcolor.name)
            self.app.cursor_position = self.cursor_screen_offset
        else:
            cursor.hide()

    def _watch_has_focus(self, focus: bool) -> None:
        super()._watch_has_focus(focus)
        self._show_slim_cursor()

    def on_unmount(self) -> None:
        slim_cursor(self.app).hide()

    def show_selection(self, anchor: Tuple[int, int], linewise: bool) -> None:
        """
        Select from `anchor` to the cursor, both characters taken. The cursor is
        the TextArea's selection end, so it's the far end that gives: one past
        `anchor` when going back, the far line end in V-LINE. The cursor's own
        cell shows it taken; V-LINE's whole lines are drawn as spans.
        """

        head = self.cursor_location
        document = self.document
        assert isinstance(document, FoldedDocument)

        top, bottom = sorted((anchor[0], head[0]))

        # Its rows go raw before the anchor is placed: its column is a stored one
        if document.show_raw(range(top, bottom + 1)):
            self._refold()

        if linewise:
            start = (anchor[0], 0 if anchor[0] <= head[0] else len(self._stored_line(anchor[0])))
        elif anchor <= head:
            start = anchor
        else:
            start = (anchor[0], min(anchor[1] + 1, len(self._stored_line(anchor[0]))))

        self.selection = Selection(start, head)
        self._visual_selection = self.selection

        rows = range(top, bottom + 1) if linewise else None

        if rows != self._selected_rows:
            self._selected_rows = rows
            self.show_overlay(self.overlay)

    def adopt_selection(self) -> None:
        """
        Hand the engine a selection made without it, by a drag or a shifted key:
        from NORMAL that's VISUAL over the characters it covers. In VISUAL a
        shifted key moves the cursor end on, a drag selects anew, and a click,
        which leaves nothing selected, goes back to NORMAL.
        """

        engine = self.engine
        selection = self.selection
        visual = engine.selection

        if selection == self._visual_selection:
            return

        if engine.mode == MODE_NORMAL and not selection.is_empty:
            engine.select_between(*self._covered(selection))
        elif visual is not None and not self.mouse_selecting:
            engine.select_between(visual[0], selection.end)
        elif visual is not None and selection.is_empty:
            engine.set_mode(MODE_NORMAL)
        elif visual is not None:
            engine.select_between(*self._covered(selection))
        else:
            return

        self.host.pending_changed()

    def _covered(
        self, selection: Selection
    ) -> Tuple[Tuple[int, int], Tuple[int, int]]:
        """
        The first and last character a TextArea selection covers, in its order:
        it stops short of its end, where VISUAL takes the cursor's character.
        Never back across a line break, so `shift+down` lands on the line below.
        """

        def before(place: Tuple[int, int]) -> Tuple[int, int]:
            return place[0], max(0, place[1] - 1)

        start, end = selection

        if start < end:
            return start, before(end)

        return before(start), end

    def replace_stored(
        self, start: Tuple[int, int], end: Tuple[int, int], text: str
    ) -> None:
        """Replace a range given in stored columns, on whatever rows it reaches."""

        document = self.document
        assert isinstance(document, FoldedDocument)

        # What's on show may be about to go, and its places with it
        self._find_view = None
        self.show_overlay(None)

        # A column means a drawn one until the row is raw; these are stored ones
        document.show_raw(range(start[0], end[0] + 1))

        self.replace(text, start, end, maintain_selection_offset=False)

    def write_pasted(self, text: str) -> None:
        """Write pasted text in at the cursor, as `ClipboardEditing` reads a paste."""

        raise NotImplementedError

    def _undo_batch(self, edits: Sequence[Edit]) -> None:
        super()._undo_batch(edits)
        self._go_to_step_start(edits)

    def _redo_batch(self, edits: Sequence[Edit]) -> None:
        super()._redo_batch(edits)
        self._go_to_step_start(edits)

    def _go_to_step_start(self, step: Sequence[Edit]) -> None:
        """An edit only knows where it was made; a step goes back to where it began."""

        assert isinstance(step, UndoStep)

        if step.cursor is None:
            return

        row = min(step.cursor[0], self.document.line_count - 1)

        # As in `NoteBuffer.move_cursor`: only a raw row takes a stored column
        self.move_cursor((row, 0))
        self.move_cursor((row, step.cursor[1]))

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

    def show_vim_flash(self) -> None:
        """Draw the matches and labels of the vim_flash the engine has open."""

        view = self.engine.vim_flash_view

        if view != self._vim_flash_view:
            self._vim_flash_view = view
            self.show_overlay(self._vim_flash_overlay(view) if view else None)

    def show_search(self) -> None:
        """Draw the matches of whichever search the engine now has on show."""

        search = self.engine.lit_search

        if search != self._shown_search:
            self._shown_search = search
            self.show_overlay(self.overlay)

    def show_yank(self) -> None:
        """Light up what the engine just yanked, if it did, for `YANK_FLASH`."""

        yanked = self.engine.yanked

        if yanked is None:
            return

        self._yank_spans = self._yank_spans_of(yanked)
        self._yank_timer = self.set_timer(YANK_FLASH, self.end_yank_flash)
        self.show_overlay(self.overlay)

    def end_yank_flash(self) -> None:
        """Put out the yank flash, whether its time is up or another key came."""

        if self._yank_timer is not None:
            self._yank_timer.stop()
            self._yank_timer = None

        if self._yank_spans:
            self._yank_spans = ()
            self.show_overlay(self.overlay)

    def _yank_spans_of(self, yanked: YankedRange) -> Sequence[OverlaySpan]:
        """The yanked range, row by row; whole lines in full."""

        (top, first), (bottom, last) = yanked.start, yanked.end

        return [
            (
                row,
                0 if yanked.linewise or row > top else first,
                len(self._stored_line(row))
                if yanked.linewise or row < bottom
                else last,
                YANKED,
            )
            for row in range(top, bottom + 1)
        ]

    def standing_spans(self) -> Sequence[OverlaySpan]:
        if self._engine is None:
            return ()

        line_count = self.document.line_count
        lines = [
            (row, 0, len(self._stored_line(row)), SELECTED)
            for row in self._selected_rows or ()
            if row < line_count
        ]

        # Over the selection and the matches, as the last thing done
        yanked = [span for span in self._yank_spans if span[0] < line_count]

        return [
            *lines,
            *((*match, SEARCH_MATCH) for match in self._engine.search_matches),
            *yanked,
        ]

    @on(TextArea.SelectionChanged)
    def _cursor_moved(self) -> None:
        """A click or a drag moves the cursor with no key for the engine to see."""

        self.adopt_selection()
        self.show_find_view()
        self.show_vim_flash()

    def _vim_flash_overlay(self, view: VimFlashView) -> Overlay:
        def is_first(match: VimFlashMatch) -> bool:
            return (match.row, match.start) == view.first

        # With overlapping matches, it's the one `enter` goes to that stays on top
        matches = sorted(view.matches, key=is_first)

        return Overlay(
            range(self.document.line_count),
            [
                (
                    match.row,
                    match.start,
                    match.end,
                    MARKED_FIRST if is_first(match) else MARKED,
                )
                for match in matches
            ],
            [
                (match.row, match.label_column, match.label, TARGET)
                for match in view.matches
                if match.label
            ],
        )

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
