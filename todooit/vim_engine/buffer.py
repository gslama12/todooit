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

    def replace(
        self, start: Tuple[int, int], end: Tuple[int, int], text: str
    ) -> None:
        """
        Put `text` in place of what's from `start` up to `end`, both raw places
        and in order. Anything that follows from the edit, like a list counted
        again, is the host's. The engine places the cursor straight after this.
        """

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

    def open_link(self) -> None:
        """Open the link under the cursor, or say there is none."""

    def pick_files(self) -> None:
        """Hand the keyboard to the files kept beside the text."""

    def list_prefix(self, row: int) -> str:
        """What opens `row` and carries on to a new line: quote, indent, marker."""

    def mode_changed(self, mode: str) -> None:
        """The engine changed mode. The cursor is checked straight after this."""
