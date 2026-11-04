"""
Markup rendered as it's typed: a finished mark becomes its drawn form on the spot
"""

from typing import Optional, Tuple

from todooit.utils.links import EMPH_MARK

from .markup import (
    BULLET_MARKS,
    DASHES,
    EMPH_STAR,
    HEADER_MARK,
    HEADER_WIDTH,
    QUOTE_GLYPH,
    QUOTE_MARK,
    RULE,
    bullet_glyph,
    indent_depth,
    split_quote,
    star_closing,
    star_pair,
)
from .view import NoteView


class TypedMarkupView(NoteView):
    """Draws `- `, `1. `, `> `, `# `, `---` and `*stars*` as they're completed."""

    def _line_head(self, row: int, column: int) -> Tuple[str, str, str]:
        """
        Split the text before the cursor into (quote bar, indent, head): the
        bar is checked first, so a mark after it opens inside the quote.
        """

        bar, body = split_quote(self.document[row])
        before = body[: max(0, column - len(bar))]
        indent = before[: len(before) - len(before.lstrip(" \t"))]

        return bar, indent, before[len(indent) :]

    def _open_bullet(self, row: int, start: int, end: int, indent: str) -> None:
        """Swap the typed mark between `start` and `end` for the glyph its depth wears."""

        glyph = bullet_glyph(indent_depth(indent))

        self.replace(glyph, (row, start), (row, end), maintain_selection_offset=False)
        self.move_cursor((row, start + len(glyph)))

    @property
    def rule(self) -> str:
        """
        A rule as wide as allowed (HEADER_WIDTH, or the window if narrower), so it never wraps.
        """

        return RULE * max(3, min(HEADER_WIDTH, self.wrap_width or HEADER_WIDTH))

    def _title_above(self, row: int) -> bool:
        """
        Whether `row` has non-blank text directly above it (title vs. bare separator).
        """

        return row > 0 and bool(self.document[row - 1].strip())

    def _draw_header(self, row: int, column: int) -> None:
        """
        Swap the `#` on `row` for a title line plus its closing rule.

        Text after the mark becomes the title (may be empty). Indent on the `#` is dropped - a header is a full top-level line.
        """

        title = self.document[row][column:].strip()

        self.replace(
            title + "\n" + self.rule,
            (row, 0),
            (row, len(self.document[row])),
            maintain_selection_offset=False,
        )
        self.move_cursor((row, 0))

    def _draw_separator(self, row: int) -> None:
        """
        Swap the `---` on `row` for the rule, inserting a blank line above first if there's text directly above (else it'd read as a header's underline).
        """

        line = self.document[row]
        lead = "\n" if self._title_above(row) else ""

        self.replace(
            lead + self.rule,
            (row, 0),
            (row, len(line)),
            maintain_selection_offset=False,
        )
        self.move_cursor((row + len(lead), len(self.rule)))

    def _render_typed(self, character: Optional[str]) -> bool:
        """
        Draw the mark that `character` completes; True if it did, in which
        case the character itself isn't typed.
        """

        if character == EMPH_STAR and self.selection.is_empty:
            row, column = self.cursor_location
            line = self.document[row]
            opening = star_pair(line, column)
            closing = star_closing(line, column) if opening is None else None

            # Star finishing a pair, whichever end went in last: swap both for zero-width emphasis marks.
            if opening is not None or closing is not None:
                # One rewrite of the whole `*phrase*`: the stars take columns the
                # marks don't, so a separate second edit would land one column off.
                start, end = (opening, column) if opening is not None else (column, closing + 1)
                phrase = line[start:end].strip(EMPH_STAR)

                self.replace(
                    EMPH_MARK + phrase + EMPH_MARK,
                    (row, start),
                    (row, end),
                    maintain_selection_offset=False,
                )

                # Land outside the emphasis: past it after a closing star, in front after an opening one.
                self.move_cursor((row, start + len(phrase) if opening is not None else start))
                return True

        if character == DASHES[0]:
            row, column = self.cursor_location

            # Third dash of a `---` alone on the line: swap for the rule immediately.
            if self.document[row] == DASHES and column == len(DASHES):
                self._draw_separator(row)
                return True

        if character in BULLET_MARKS and self.selection.is_empty:
            row, column = self.cursor_location
            bar, indent, head = self._line_head(row, column)

            after = self.document[row][column:]

            # Mark put at the head of a line whose words already have a space in
            # front: that space is the mark's own, so the bullet opens now. Just
            # the one space, so a mark typed into an indent stays literal.
            if not head and after[:1] == " " and not after[1:2].isspace():
                self._open_bullet(row, column, column + 1, indent)
                return True

        if character == " ":
            row, column = self.cursor_location

            # Space of `> `, `- `, `* ` or `# `: only bar/indent may precede the
            # mark. Judged on the text before the cursor, so a mark in front of
            # existing words still opens its line.
            bar, indent, head = self._line_head(row, column)
            at = len(bar) + len(indent)

            # Headers and quotes are whole-line constructs, meaningless nested in another quote.
            if not bar and head and set(head) == {HEADER_MARK}:
                self._draw_header(row, column)
                return True

            if not bar and head == QUOTE_MARK:
                self.replace(
                    QUOTE_GLYPH, (row, at), (row, column),
                    maintain_selection_offset=False,
                )
                self.move_cursor((row, at + len(QUOTE_GLYPH)))
                return True

            if head in BULLET_MARKS:
                self._open_bullet(row, at, column, indent)
                return True

        return False
