"""
What the engine needs from the text it edits, so it never imports its host
"""

from typing import Callable, Protocol, Tuple


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

    def drawn_line(self, row: int) -> str:
        """`row` as the reader sees it right now, which is all `vim_flash` looks at."""

    def stored_column(self, row: int, column: int) -> int:
        """The raw column of the character drawn at `column` of `row`."""

    @property
    def cursor(self) -> Tuple[int, int]:
        """Where the cursor is."""

    def move_cursor(self, row: int, column: int) -> None:
        """Put the cursor at this place, which the engine has checked. Ends any selection."""

    def select(self, anchor: Tuple[int, int], linewise: bool) -> None:
        """
        Show what VISUAL has selected: from `anchor` to the cursor, the characters
        at both ends taken, or with `linewise` every whole line from one to the
        other. Asked again after each key in VISUAL; moving the cursor ends it.
        """

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

    def show_help(self) -> None:
        """Show every key the editor knows."""

    def list_prefix(self, row: int) -> str:
        """What opens `row` and carries on to a new line: quote, indent, marker."""

    def nesting_start(self, row: int) -> int:
        """The column `row`'s indent starts at: past its quote bar, if it has one."""

    def mode_changed(self, mode: str) -> None:
        """The engine changed mode. The cursor is checked straight after this."""

    def begin_undo_step(self) -> None:
        """Every edit from here on, the host's own too, is one undo step."""

    def end_undo_step(self) -> None:
        """The step is finished. With no edits in it, it never happened."""

    def undo(self) -> None:
        """Take back the last step, if any, and go to where the cursor was before it."""

    def redo(self) -> None:
        """Put back the last step undone, if any, the cursor going to the same place."""

    def report(self, message: str) -> None:
        """Show the user a short message, in plain text."""

    def prompt_changed(self) -> None:
        """The search prompt opened, changed or closed: redraw whatever shows it."""

    def copy_to_clipboard(self, text: str) -> None:
        """Put `text` on the system clipboard."""

    def clipboard_text(self) -> str:
        """What the system clipboard holds, or "" if nothing can be had."""

    def start_reading_clipboard(self) -> Callable[[], str]:
        """
        Start reading `clipboard_text` as it stands now, without making the key
        wait. What's returned gives the answer, waiting for it if need be.
        """

    def paste_clipboard_text(self, text: str) -> None:
        """
        Write text off the system clipboard in at the cursor, however the host
        reads a paste, and leave the cursor after it. Only ever called in INSERT.
        """
