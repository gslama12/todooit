"""
What the engine needs from the text it edits, so it never imports its host
"""

from typing import Protocol, Tuple


class Buffer(Protocol):
    """Text in lines and a cursor, as (row, column) into the raw text."""

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

    def mode_changed(self, mode: str) -> None:
        """The engine changed mode. The cursor is checked straight after this."""
