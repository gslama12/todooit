"""
NORMAL mode: what each key does while the note is being read
"""

from todooit.utils.links import folded_link_at

from ..disp.markup import line_prefix
from .editing import TextEditing

# Line ends. The direction keys and `i` are the engine's; these are on their way.
NORMAL_MOTIONS = {
    "0": "cursor_line_start",
    "$": "cursor_line_end",
}

# Scroll keys, on vim's u/d; bare since NORMAL is read-only.
HALF_PAGE_UP = "u"
HALF_PAGE_DOWN = "d"


class NormalKeys(TextEditing):
    """The NORMAL-mode keys, and the moves only they make."""

    def __init__(self, text: str) -> None:
        super().__init__(text)

    def _handle_normal_key(self, key: str) -> bool:
        """
        Handle a NORMAL-mode key; True if handled (others fall through, keeping shift-motions/clipboard bindings shared with INSERT).
        """

        if motion := NORMAL_MOTIONS.get(key):
            getattr(self, f"action_{motion}")()
            return True

        if key in (HALF_PAGE_UP, HALF_PAGE_DOWN):
            half = self.half_page()
            self.engine.buffer.scroll_rows(-half if key == HALF_PAGE_UP else half)
            return True

        if key == "o":
            self._open_link_under_cursor()
            return True

        if key == "O":
            self._open_line()
            return True

        return False

    def _open_link_under_cursor(self) -> None:
        """
        Open the link under the cursor, or report none; never enters INSERT.
        """

        row, column = self.cursor_location
        link = folded_link_at(self._stored_line(row), column, raw=True)

        if link is None:
            self.host.report("No link under the cursor")
            return

        self.host.open_link(link.url)

    def _open_line(self) -> None:
        """
        Start a new line below this one, in INSERT.

        Shifted (`O`), since lowercase `o` opens links. Carries over the
        bullet/quote prefix, like `enter` does.
        """

        row, _ = self.cursor_location
        line = self.document[row]
        prefix = line_prefix(line)

        self.enter_insert()

        self.move_cursor((row, len(line)))
        self.insert("\n" + prefix, maintain_selection_offset=False)
        self._recount(row + 1)
