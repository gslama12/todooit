"""
The note as the text the vim engine works on
"""

from typing import TYPE_CHECKING, Tuple

if TYPE_CHECKING:  # pragma: no cover
    from .modes import ModalEditor


class NoteBuffer:
    """Implements the engine's `Buffer` on the note's editor."""

    def __init__(self, editor: "ModalEditor") -> None:
        self._editor = editor

    def line(self, row: int) -> str:
        return self._editor._stored_line(row)

    @property
    def cursor(self) -> Tuple[int, int]:
        return self._editor.cursor_location

    def move_cursor(self, row: int, column: int) -> None:
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

    def mode_changed(self, mode: str) -> None:
        self._editor.show_mode(mode)
