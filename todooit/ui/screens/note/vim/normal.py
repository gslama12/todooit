"""
NORMAL mode: what each key does while the note is being read
"""

from ..disp.markup import line_prefix
from .editing import TextEditing


class NormalKeys(TextEditing):
    """The NORMAL-mode keys, and the moves only they make."""

    def __init__(self, text: str) -> None:
        super().__init__(text)

    def _handle_normal_key(self, key: str) -> bool:
        """
        Handle a NORMAL-mode key; True if handled (others fall through, keeping shift-motions/clipboard bindings shared with INSERT).
        """

        if key == "O":
            self._open_line()
            return True

        return False

    def _open_line(self) -> None:
        """
        Start a new line below this one, in INSERT.

        Carries over the bullet/quote prefix, like `enter` does.
        """

        row, _ = self.cursor_location
        line = self.document[row]
        prefix = line_prefix(line)

        self.enter_insert()

        self.move_cursor((row, len(line)))
        self.insert("\n" + prefix, maintain_selection_offset=False)
        self._recount(row + 1)
