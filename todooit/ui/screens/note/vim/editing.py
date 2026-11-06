"""
Editing keys: enter, nesting, clearing, and keeping numbered lists counted
"""

from textual.widgets.text_area import Location

from ..disp.document import FoldedDocument
from ..disp.markup import (
    INDENT,
    indent_depth,
    line_prefix,
    marker_start,
    recount,
    split_indent,
    split_quote,
)
from .modes import ModalEditor


class TextEditing(ModalEditor):
    """What a key does to the text around the cursor, list items above all."""

    def _handle_enter(self) -> bool:
        """
        Enter where the line's markup decides what it does; True if handled,
        False to let it type a plain newline.
        """

        row, column = self.cursor_location
        line = self.document[row]

        prefix = line_prefix(line)

        if not prefix:
            return False

        glyph_at = marker_start(line)

        if column < len(prefix):
            # Cursor in the indent/marker: open a blank line above and
            # move this whole item down, rather than give it a second marker.
            self.insert("\n", (row, 0), maintain_selection_offset=False)
            self.move_cursor((row + 1, column))
        elif line[len(prefix) :].strip():
            self.insert("\n" + prefix, maintain_selection_offset=False)
            self._recount(row + 1)
        elif self._nested_item(row):
            # Empty nested item: dedent one level (far more common
            # than deleting it). Marker only goes at the top level.
            self._set_depth(row, -1)
        else:
            # Empty top-level item: remove just the marker (a quoted
            # bullet loses the bullet first; the quote ends on the next enter).
            self.replace("", (row, glyph_at), (row, len(line)))
            self.move_cursor((row, glyph_at))

        return True

    def _nested_item(self, row: int) -> bool:
        """
        Whether the list item on `row` is nested (checked via indent, not the glyph; quoted items are measured after the bar).
        """

        _, body = split_quote(self.document[row])
        indent, bullet, _ = split_indent(body)

        return bool(bullet) and indent_depth(indent) > 0

    def _set_depth(self, row: int, levels: int) -> None:
        """
        Move a line `levels` steps in/out, rewriting its indent (snapping off-level indents). A quoted line nests after its bar, which stays put.
        """

        # Stored line, not folded: rewriting folded text would overwrite link
        # addresses with their display names.
        line = self._stored_line(row)
        bar, body = split_quote(line)
        indent, bullet, rest = split_indent(body)

        depth = max(0, indent_depth(indent) + levels)

        # A number is put right by the recount below
        head = bar + INDENT * depth + bullet

        if head + rest == line:
            return

        _, column = self.cursor_location
        self.replace(
            head + rest,
            (row, 0),
            (row, len(self.document[row])),
            maintain_selection_offset=False,
        )

        # Cursor follows the words, not the column: indenting moves the words.
        self.move_cursor((row, max(0, column + len(head) - len(bar + indent + bullet))))

        self._recount(row)

    def _recount(self, row: int) -> None:
        """
        Number the list `row` sits in again (a no-op off a list); the cursor stays on its words.
        """

        document = self.document
        assert isinstance(document, FoldedDocument)

        for at, start, end, marker in recount(document.stored_lines, row):
            self.replace(marker, (at, start), (at, end), maintain_selection_offset=True)

    def _delete_via_keyboard(self, start: Location, end: Location):
        result = super()._delete_via_keyboard(start, end)
        self._recount_edit(start, end, result)

        return result

    def _replace_via_keyboard(self, insert: str, start: Location, end: Location):
        result = super()._replace_via_keyboard(insert, start, end)
        self._recount_edit(start, end, result)

        return result

    def _recount_edit(self, start: Location, end: Location, result) -> None:
        """
        Whatever a key typed or deleted, count the lists on the lines it left
        behind; nothing to do if read_only refused the edit.
        """

        if result is None:
            return

        for row in range(min(start, end)[0], result.end_location[0] + 1):
            self._recount(row)

    def action_indent(self) -> None:
        """
        Indent the current line one level; refused in NORMAL since this is a bare, unmodified edit key (unlike other markup, which is typed).
        """

        if self.read_only:
            return

        row, _ = self.cursor_location
        self._set_depth(row, 1)

    def action_dedent(self) -> None:
        """
        Un-nest the current line one level.
        """

        if self.read_only:
            return

        row, _ = self.cursor_location
        self._set_depth(row, -1)

    def action_note_start(self) -> None:
        self.move_cursor((0, 0))

    def action_note_end(self) -> None:
        self.move_cursor(self.document.end)

    def action_clear_note(self) -> None:
        """
        Ask to clear the whole note (INSERT only, like every edit); the screen handles the confirmation.
        """

        if self.read_only:
            return

        self.host.request_clear()
