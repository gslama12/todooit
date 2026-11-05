"""
NORMAL mode: what each key does while the note is being read
"""

from typing import Dict

from todooit.ui.api.api_components.keys import MotionKeys
from todooit.utils.links import folded_link_at

from ..disp.markup import line_prefix
from .editing import TextEditing

# Line ends; the four direction keys are the panes' own (see `normal_motions`).
# No other letter does anything.
NORMAL_MOTIONS = {
    "0": "cursor_line_start",
    "$": "cursor_line_end",
}


def normal_motions(motions: MotionKeys) -> Dict[str, str]:
    return {
        **NORMAL_MOTIONS,
        motions.left: "cursor_left",
        motions.right: "cursor_right",
        motions.up: "cursor_up",
        motions.down: "cursor_down",
    }

# Only key into INSERT; vim's a/I/A are intentionally omitted.
INSERT_ENTRY = "i"

# Scroll keys, on vim's u/d; bare since NORMAL is read-only.
HALF_PAGE_UP = "u"
HALF_PAGE_DOWN = "d"


class NormalKeys(TextEditing):
    """The NORMAL-mode keys, and the moves only they make."""

    def __init__(self, text: str) -> None:
        super().__init__(text)

        # Set by the first `g` of a `gg` chord.
        self._pending_g = False

    def _handle_normal_key(self, key: str) -> bool:
        """
        Handle a NORMAL-mode key; True if handled (others fall through, keeping shift-motions/clipboard bindings shared with INSERT).
        """

        # Only the key right after a `g` can complete a `gg`.
        pending_g, self._pending_g = self._pending_g, False

        if key == "g":
            if pending_g:
                self.move_cursor((0, 0))
            else:
                self._pending_g = True

            return True

        if motion := normal_motions(self.app.api.motion_keys()).get(key):
            getattr(self, f"action_{motion}")()
            return True

        if key == "G":
            self.move_cursor(self.document.end)
            return True

        if key == INSERT_ENTRY:
            self.enter_insert()
            return True

        if key in (HALF_PAGE_UP, HALF_PAGE_DOWN):
            self.scroll_half_page(key == HALF_PAGE_UP)
            return True

        if key == "f":
            self.host.pick_files()
            return True

        if key == "o":
            self._open_link_under_cursor()
            return True

        if key == "O":
            self._open_line()
            return True

        return False

    def half_page(self) -> int:
        """
        Half the window height, never less than a line, so scroll distance matches the terminal size.
        """

        return max(1, self.content_size.height // 2)

    def scroll_half_page(self, up: bool) -> None:
        """
        Move cursor and view half a window (vim's ctrl+u/ctrl+d). Cursor steps via cursor_up/down, since a wrapped line spans several rows but is one row in the document; scroll_to clamps at the note's ends.
        """

        half = self.half_page()
        step = self.action_cursor_up if up else self.action_cursor_down
        target = self.scroll_offset.y + (-half if up else half)

        for _ in range(half):
            step()

        self.scroll_to(y=target, animate=False)

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
