"""
Editing keys: enter, backspace, nesting, clearing
"""

from typing import Optional, Tuple

from todooit.utils.links import folded_emph

from ..disp.markup import (
    INDENT,
    RULE_RE,
    bullet_glyph,
    indent_depth,
    item_number,
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

        below = row + 1
        closed = (
            column == len(line)
            and below < self.document.line_count
            and RULE_RE.match(self.document[below])
        )

        if closed:
            # Title + rule are one unit; enter from the title's end skips the rule into the section.
            if below + 1 >= self.document.line_count:
                self.insert(
                    "\n",
                    (below, len(self.document[below])),
                    maintain_selection_offset=False,
                )

            self.move_cursor((below + 1, 0))
            return True

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

    def _handle_backspace(self) -> bool:
        """
        Backspace where the (invisible) markup decides what it does; True if
        handled, False to let it delete a plain character.
        """

        row, column = self.cursor_location
        pair = self._emph_ending_at(row, column)

        if pair is not None:
            # Cursor sits right after an emphasis's closing mark: backspace
            # removes the emphasis instead of eating the last letter (marks are invisible).
            self._take_emph_off(row, column, pair)
            return True

        line = self.document[row]
        _, body = split_quote(line)
        _, bullet, _ = split_indent(body)

        if not bullet or not 0 < column <= len(line_prefix(line)):
            return False

        # In the marker/indent: dedent one level (like enter on an
        # empty item), rather than bite a glyph in half or eat the indent space by space.
        if self._nested_item(row):
            self._set_depth(row, -1)
        else:
            # A quoted item loses its bullet first; the quote ends on the next backspace.
            glyph_at = marker_start(line)

            self.replace(
                "",
                (row, glyph_at),
                (row, len(line_prefix(line))),
                maintain_selection_offset=False,
            )
            self.move_cursor((row, glyph_at))

        return True

    def _emph_ending_at(
        self, row: int, column: int
    ) -> Optional[Tuple[int, int]]:
        """
        (start, end) of an emphasised phrase if the cursor sits right at its end, else None - that's where backspace removes the (invisible) marks.
        """

        # Only ever asked about the cursor's row, which is raw
        for start, end in folded_emph(self._stored_line(row), raw=True):
            if column == end:
                return start, end

        return None

    def _take_emph_off(self, row: int, column: int, pair: Tuple[int, int]) -> None:
        """
        Remove both emphasis marks in `pair`, keeping the words (one replace - the marks are folded off-page, with no column to delete individually).
        """

        start, end = pair

        self.replace(
            self.document[row][start:end],
            (row, start),
            (row, end),
            maintain_selection_offset=False,
        )

        self.move_cursor((row, end))

    def _nested_item(self, row: int) -> bool:
        """
        Whether the list item on `row` is nested (checked via indent, not the glyph; quoted items are measured after the bar).
        """

        _, body = split_quote(self.document[row])
        indent, bullet, _ = split_indent(body)

        return bool(bullet) and indent_depth(indent) > 0

    def _set_depth(self, row: int, levels: int) -> None:
        """
        Move a line `levels` steps in/out, rewriting its indent (snapping off-level indents) and re-glyphing the bullet. A quoted line nests after its bar, which stays put.
        """

        # Stored line, not folded: rewriting folded text would overwrite link
        # addresses with their display names.
        line = self._stored_line(row)
        bar, body = split_quote(line)
        indent, bullet, rest = split_indent(body)

        depth = max(0, indent_depth(indent) + levels)

        # A glyph shows its depth; a number is put right by the recount below
        marker = bullet_glyph(depth) if item_number(bullet) is None else bullet
        head = bar + INDENT * depth + (marker if bullet else "")

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

        for at, start, end, marker in recount(self.document.lines, row):
            self.replace(marker, (at, start), (at, end), maintain_selection_offset=True)

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

    def action_clear_line(self) -> None:
        """
        Empty the cursor's line, keeping the line itself (INSERT only, like every edit).
        """

        if self.read_only:
            return

        row, _ = self.cursor_location
        self._delete_via_keyboard((row, 0), (row, len(self.document[row])))

    def action_clear_note(self) -> None:
        """
        Ask to clear the whole note; the screen handles the confirmation.
        """

        self.host.request_clear()
