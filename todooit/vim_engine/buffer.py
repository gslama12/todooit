"""
What the engine needs from the text it edits, so it never imports its host
"""

from typing import Protocol, Tuple


class Buffer(Protocol):
    """Text in lines and a cursor, as (row, column) into the raw text."""

    @property
    def line_count(self) -> int:
        """How many lines there are; an empty text still has one."""

    @property
    def visible_rows(self) -> range:
        """The lines on screen, in whole or in part."""

    def line(self, row: int) -> str:
        """The raw text of `row`."""

    @property
    def cursor(self) -> Tuple[int, int]:
        """Where the cursor is."""

    def move_cursor(self, row: int, column: int) -> None:
        """Put the cursor at this place, which the engine has checked."""

    def move_rows(self, delta: int) -> None:
        """
        Move up (negative) or down by rows as the reader sees them, stopping at
        the ends of the text. Wrapping and the column to keep are the host's.
        """

    def move_lines(self, delta: int) -> None:
        """
        Move up (negative) or down by lines of the text, however they wrap,
        stopping at the ends of the text. The column to keep is the host's.
        """

    @property
    def half_page(self) -> int:
        """How many rows half a page is, as the reader sees them."""

    def scroll_rows(self, delta: int) -> None:
        """Move the cursor and the view together, up (negative) or down by rows."""

    def center_view(self) -> None:
        """Bring the cursor to the middle of the view, without moving it."""

    def mode_changed(self, mode: str) -> None:
        """The engine changed mode. The cursor is checked straight after this."""
