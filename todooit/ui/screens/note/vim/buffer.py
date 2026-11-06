"""
The note as the text the vim engine works on
"""

from typing import TYPE_CHECKING, Tuple

from ..disp.document import HangingDocument

if TYPE_CHECKING:  # pragma: no cover
    from .modes import ModalEditor


class NoteBuffer:
    """Implements the engine's `Buffer` on the note's editor."""

    def __init__(self, editor: "ModalEditor") -> None:
        self._editor = editor

    @property
    def line_count(self) -> int:
        return self._editor.document.line_count

    @property
    def visible_rows(self) -> range:
        editor = self._editor
        wrapped = editor.wrapped_document
        assert isinstance(wrapped, HangingDocument)

        top = wrapped.row_at(editor.scroll_offset.y)
        bottom = wrapped.row_at(editor.scroll_offset.y + editor.content_size.height - 1)

        return range(
            top[0] if top else 0, bottom[0] + 1 if bottom else self.line_count
        )

    def line(self, row: int) -> str:
        return self._editor._stored_line(row)

    @property
    def cursor(self) -> Tuple[int, int]:
        return self._editor.cursor_location

    def move_cursor(self, row: int, column: int) -> None:
        # A column means a drawn one until the row is raw; ours is a stored one
        if row != self.cursor[0]:
            self._editor.move_cursor((row, 0))

        self._editor.move_cursor((row, column))

    def move_rows(self, delta: int) -> None:
        editor = self._editor
        navigator = editor.navigator

        for _ in range(abs(delta)):
            location = editor.cursor_location

            # TextArea runs on to the end of the line; vim stays where it is
            if delta < 0:
                if navigator.is_first_wrapped_line(location):
                    return
                editor.action_cursor_up()
            else:
                if navigator.is_last_wrapped_line(location):
                    return
                editor.action_cursor_down()

    def move_lines(self, delta: int) -> None:
        editor = self._editor
        row, column = self.cursor
        target = max(0, min(row + delta, self.line_count - 1))

        if target == row:
            return

        # The column it's been keeping, across any lines too short for it. Left
        # unrecorded, so a run of these keeps it too.
        wanted = max(column, editor.navigator.last_x_offset)

        # As in `move_cursor`: only a raw row takes a stored column
        editor.move_cursor((target, 0), record_width=False)
        editor.move_cursor((target, wanted), record_width=False)

    @property
    def half_page(self) -> int:
        return self._editor.half_page()

    def scroll_rows(self, delta: int) -> None:
        editor = self._editor
        target = editor.scroll_offset.y + delta

        self.move_rows(delta)

        # The view goes where it's told, so here it's the cursor that gives way.
        # Lines unfold and fold again under it, so the rows it crosses aren't the
        # rows it gains: it walks until it's there, one way only.
        way = 0

        while True:
            top = max(0, min(target, editor.max_scroll_y))
            first, last = editor.rows_with_context(top)
            y = editor.cursor_y
            gap = max(first - y, 0) + min(last - y, 0)
            place = self.cursor

            if not gap or gap * way < 0:
                break

            way = gap
            self.move_rows(gap)

            if self.cursor == place:
                break

        # Last, since moving the cursor brings the view along behind it
        editor.scroll_to(y=top, animate=False, immediate=True)

    def center_view(self) -> None:
        self._editor.scroll_cursor_visible(center=True)

    def mode_changed(self, mode: str) -> None:
        self._editor.show_mode(mode)
