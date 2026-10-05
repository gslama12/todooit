"""
TextArea documents that fold links/emphasis out of view and hang wrapped lines
"""

from bisect import bisect_right
from typing import List, Optional, Tuple

from rich.cells import cell_len
from textual._wrap import compute_wrap_offsets
from textual.expand_tabs import get_tab_widths
from textual.geometry import Offset
from textual.document._document import Document, EditResult
from textual.document._document_navigator import DocumentNavigator
from textual.document._wrapped_document import WrappedDocument

from todooit.utils import fold_links
from todooit.utils.links import (
    drawn_column,
    stored_range,
)

from .markup import (
    WRAP_MIN,
    hanging_prefix,
)


class FoldedDocument(Document):
    """
    The note as stored, handed out folded (links shortened to their names) as
    drawn. The only place the two differ - everything above this class works
    in drawn columns, everything below in stored ones. A folded link has no
    cursor column inside its name, so an edit reaching into one is widened to
    cover the whole `[name](url)`.
    """

    def _line(self, row: int) -> str:
        """One stored line; `row` is clamped into range."""

        return self._lines[max(0, min(row, len(self._lines) - 1))]

    @property
    def lines(self) -> list:
        return [fold_links(line)[0] for line in self._lines]

    @property
    def stored_lines(self) -> list:
        """The note as written, which is what a save writes out."""

        return self._lines

    def stored_line(self, row: int) -> str:
        """One line as written, for rewrites that need to preserve its markup."""

        return self._line(row)

    def get_line(self, index: int) -> str:
        return fold_links(self._lines[index])[0]

    def __getitem__(self, line_index):
        if isinstance(line_index, slice):
            return [fold_links(line)[0] for line in self._lines[line_index]]

        return fold_links(self._lines[line_index])[0]

    @property
    def end(self) -> tuple:
        return (self.line_count - 1, len(self.get_line(self.line_count - 1)))

    def _drawn(self, location: tuple) -> tuple:
        row, column = location

        return row, drawn_column(self._line(row), column)

    def _stored_span(self, start: tuple, end: tuple) -> tuple:
        """
        A drawn-page range, translated to the stored-note range behind it.
        Single-line ranges resolve whole (a link's columns depend on both
        ends); multi-line ranges are cut and resolved per line.
        """

        (top_row, top_column), (bottom_row, bottom_column) = start, end
        top_line = self._line(top_row)
        bottom_line = self._line(bottom_row)

        if top_row == bottom_row:
            opening, closing = stored_range(top_line, top_column, bottom_column)
        else:
            opening, _ = stored_range(
                top_line, top_column, len(fold_links(top_line)[0])
            )
            _, closing = stored_range(bottom_line, 0, bottom_column)

        return (top_row, opening), (bottom_row, closing)

    def replace_range(self, start: tuple, end: tuple, text: str):
        top, bottom = self._stored_span(*sorted((start, end)))

        result = super().replace_range(top, bottom, text)

        # Convert the edit's end back to drawn columns for the caller's cursor
        return EditResult(self._drawn(result.end_location), result.replaced_text)

    def get_text_range(self, start: tuple, end: tuple) -> str:
        # Returns the stored text, so a copied link carries its full address
        top, bottom = self._stored_span(*sorted((start, end)))

        return super().get_text_range(top, bottom)


class HangingDocument(WrappedDocument):
    """
    Wraps a line with every row after the first pushed in under the first
    row's words, instead of upstream's flush-left wrapping (which would draw
    a wrapped bullet's second row outside the list). The indent is purely a
    page thing, never written into the text. Columns in and out are always
    screen columns (indent included), so clicks and vertical cursor movement
    land correctly.
    """

    def wrap(self, width: int, tab_width: Optional[int] = None) -> None:
        """
        Wrap every line at its own width, caching results by line text keyed
        to the previous wrap at the same width (so a keystroke only re-measures
        the changed line). Cache is dropped on width change.
        """

        same_shape = width == self._width and tab_width in (None, self._tab_width)
        wrapped_before = getattr(self, "_wrap_cache", {}) if same_shape else {}
        wrap_cache = {}

        self._width = width

        if tab_width:
            self._tab_width = tab_width

        wrap_offsets: List[List[int]] = []
        hanging: List[int] = []
        tab_widths: List[List[int]] = []
        offset_to_line_info: List[Tuple[int, int]] = []
        line_index_to_offsets: List[List[int]] = []

        current_offset = 0

        for line_index, line in enumerate(self.document.lines):
            if line in wrapped_before:
                offsets, pad = wrapped_before[line]
            else:
                offsets, pad = self._wrap_line(line)

            wrap_cache[line] = (offsets, pad)
            sections = get_tab_widths(line, self._tab_width)

            wrap_offsets.append(offsets)
            hanging.append(pad)
            tab_widths.append([section_width for _, section_width in sections])
            line_index_to_offsets.append([])

            for section_offset in range(len(offsets) + 1):
                offset_to_line_info.append((line_index, section_offset))
                line_index_to_offsets[line_index].append(current_offset)
                current_offset += 1

        self._wrap_cache = wrap_cache
        self._wrap_offsets = wrap_offsets
        self._hanging = hanging
        self._tab_width_cache = tab_widths
        self._offset_to_line_info = offset_to_line_info
        self._line_index_to_offsets = line_index_to_offsets

    def wrap_range(self, start: tuple, old_end: tuple, new_end: tuple) -> None:
        """
        Re-wrap by wrapping the whole note again, rather than upstream's
        incremental re-wrap of just the touched lines - cheaper for a note-sized
        document than an incremental path rewritten for per-line widths.
        """

        self.wrap(self._width)

    def _wrap_line(self, line: str) -> Tuple[List[int], int]:
        """
        Where `line` breaks, and how far rows after the first are pushed in.
        The first row is full window width; later rows are narrower by the
        indent, so breaks are found one row at a time. No indent -> upstream wrap.
        """

        width = self._width

        if not width:
            return [], 0

        tab_width = self._tab_width
        prefix = hanging_prefix(line)
        hanging = cell_len(prefix.expandtabs(tab_width))

        # No indent to hang, or too little room left to read after hanging it
        if not hanging or width - hanging < WRAP_MIN:
            return compute_wrap_offsets(line, width, tab_width), 0

        offsets: List[int] = []
        start = 0
        room = width

        while start < len(line):
            breaks = compute_wrap_offsets(line[start:], room, tab_width)

            if not breaks or breaks[0] <= 0:
                break

            start += breaks[0]
            offsets.append(start)
            room = width - hanging

        if not offsets:
            return [], 0

        if offsets[0] <= len(prefix):
            # First word too long to sit beside its own marker - fall back to
            # the plain wrap rather than leave the first row holding only the marker
            return compute_wrap_offsets(line, width, tab_width), 0

        return offsets, hanging

    def hanging_pad(self, line_index: int, section_offset: int) -> int:
        """Indent of the row at `section_offset` (0 for the first row); `-1` means the line's last row."""

        if section_offset == 0:
            return 0

        try:
            return self._hanging[line_index]
        except IndexError:
            return 0

    def pad_at(self, y_offset: int) -> int:
        """How far the row at `y_offset` down the document is pushed in."""

        try:
            line_index, section_offset = self._offset_to_line_info[y_offset]
        except IndexError:
            return 0

        return self.hanging_pad(line_index, section_offset)

    def location_to_offset(self, location: tuple) -> Offset:
        """Where in the window a place in the note is drawn, indent included."""

        offset = super().location_to_offset(location)
        line_index = max(0, min(location[0], len(self._wrap_offsets) - 1))
        section_offset = bisect_right(self.get_offsets(line_index), location[1])

        pad = self.hanging_pad(line_index, section_offset)

        return Offset(offset.x + pad, offset.y)

    def get_target_document_column(
        self, line_index: int, x_offset: int, y_offset: int
    ) -> int:
        """Inverse of `location_to_offset`: column at `x_offset`, indent removed."""

        pad = self.hanging_pad(line_index, y_offset)

        return super().get_target_document_column(
            line_index, max(0, x_offset - pad), y_offset
        )


class HangingNavigator(DocumentNavigator):
    """
    Moves the cursor up/down by its drawn (screen) column, not upstream's
    row-relative column, which would drift crossing an indented row.
    """

    def get_location_above(self, location: tuple) -> tuple:
        wrapped = self._wrapped_document

        if self.is_first_wrapped_line(location):
            return 0, 0

        x_offset, y_offset = wrapped.location_to_offset(location)

        return wrapped.offset_to_location(
            Offset(max(x_offset, self.last_x_offset), y_offset - 1)
        )

    def get_location_below(self, location: tuple) -> tuple:
        wrapped = self._wrapped_document

        if self.is_last_wrapped_line(location):
            # End of the note
            row = self._document.line_count - 1

            return row, len(self._document[row])

        x_offset, y_offset = wrapped.location_to_offset(location)

        return wrapped.offset_to_location(
            Offset(max(x_offset, self.last_x_offset), y_offset + 1)
        )
