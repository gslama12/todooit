"""
The text area a note is drawn in: folded markup, hanging lines, quote bars
"""

from rich.segment import Segment
from rich.style import Style
from textual import events
from textual.document._document import EditResult
from textual.strip import Strip
from textual.widgets import TextArea
from textual.widgets._text_area import Edit, Selection

from todooit.utils.links import raw_column

from .document import (
    FoldedDocument,
    HangingDocument,
    HangingNavigator,
    NoteEdit,
)
from .markup import (
    QUOTE_BAR,
    QUOTE_GLYPH,
    RULE,
    RULE_SPAN,
    heading_span,
    scan_note,
)


class NoteView(TextArea):
    """A TextArea that draws the note's markup instead of showing it raw."""

    def _set_document(self, text: str, language) -> None:
        """
        Replace the plain TextArea document with a folding one, and rewire wrapping/navigation to it.
        """

        super()._set_document(text, language)

        self.document = FoldedDocument(text)
        self.wrapped_document = HangingDocument(
            self.document, tab_width=self.indent_width
        )
        self.navigator = HangingNavigator(self.wrapped_document)

        self._build_highlight_map()
        self._rewrap_and_refresh_virtual_size()
        self.move_cursor((0, 0))

    def _validate_selection(self, selection: Selection) -> Selection:
        """
        Make the rows a selection lands on raw, before anything reads them.

        Every way of placing the cursor comes through here, each with a column
        read off the row as it looks now, so this is where a column on a folded
        row becomes the column of the same character on the raw one. A selection
        keeps all its rows raw, so the column its far end holds stays good.
        """

        document = self.document

        if not isinstance(document, FoldedDocument):
            return super()._validate_selection(selection)

        start = document.raw_location(selection.start)
        end = document.raw_location(selection.end)

        last = document.line_count - 1
        top = min(start[0], end[0], last)
        bottom = min(max(start[0], end[0]), last)

        if document.show_raw(range(top, bottom + 1)):
            self._refold()

        return super()._validate_selection(Selection(start, end))

    async def _on_mouse_down(self, event: events.MouseDown) -> None:
        """A click at the head of a folded line means the character drawn there."""

        document = self.document
        assert isinstance(document, FoldedDocument)

        row, column = self.get_target_document_location(event)
        folded = row not in document.raw_rows

        # Textual calls this on every class in turn; once is enough
        event.prevent_default()
        await super()._on_mouse_down(event)

        if folded and column == 0:
            first = raw_column(document.stored_line(row), 0)
            self.selection = Selection.cursor((row, first))

    def _refold(self) -> None:
        """Redraw after a line changed height, keeping the top of the view where it is."""

        wrapped = self.wrapped_document
        assert isinstance(wrapped, HangingDocument)

        top = wrapped.row_at(self.scroll_offset.y)

        self._rewrap_and_refresh_virtual_size()
        self._build_highlight_map()

        if top is not None and self.is_mounted:
            self.scroll_to(y=wrapped.y_of(*top), animate=False, immediate=True)

        self.refresh()

    def edit(self, edit: Edit) -> EditResult:
        return super().edit(
            NoteEdit(
                edit.text,
                edit.from_location,
                edit.to_location,
                edit.maintain_selection_offset,
            )
        )

    def _undo_batch(self, edits) -> None:
        super()._undo_batch(edits)
        self._refold()

    def _redo_batch(self, edits) -> None:
        super()._redo_batch(edits)
        self._refold()

    def _render_line(self, y: int) -> Strip:
        """A row of the note, with the wash behind it if it's a heading's."""

        strip = self._draw_row(y)
        wrapped = self.wrapped_document
        document = self.document
        assert isinstance(wrapped, HangingDocument)
        assert isinstance(document, FoldedDocument)

        found = wrapped.row_at(y + self.scroll_offset.y)
        span = heading_span(document.stored_line(found[0])) if found else None

        return self._wash(strip, span) if span else strip

    def _wash(self, strip: Strip, span: str) -> Strip:
        """
        Put the heading's background behind the whole row. Only over the note's
        own background, so the cursor and a selection still show on it.
        """

        base = self._theme.base_style
        background = base.bgcolor if base else None
        wash = Style(bgcolor=self._theme.syntax_styles[span].bgcolor)

        return Strip(
            Segment(text, style + wash, control)
            if style is not None and style.bgcolor == background
            else Segment(text, style, control)
            for text, style, control in strip
        )

    def _draw_row(self, y: int) -> Strip:
        """
        Render a wrapped continuation row, indented via blank padding columns (not real characters, so line offsets elsewhere are unaffected).
        """

        strip = super()._render_line(y)
        wrapped = self.wrapped_document
        document = self.document
        assert isinstance(wrapped, HangingDocument)
        assert isinstance(document, FoldedDocument)

        found = wrapped.row_at(y + self.scroll_offset.y)
        block = document.block_at(found[0]) if found else None

        if block:
            return self._draw_block(strip, block)

        pad = wrapped.pad_at(y + self.scroll_offset.y)

        if not pad:
            return strip

        gutter_width = self.gutter_width

        if gutter_width:
            gutter, body = strip.divide([gutter_width, strip.cell_length])
        else:
            gutter, body = None, strip

        # Blend the padding into the row's background (already full-width;
        # cursor line is lit a different color).
        segments = list(body)
        trailing = segments[-1].style if segments else None
        style = Style(bgcolor=trailing.bgcolor) if trailing else Style()

        body = body.crop_pad(max(0, body.cell_length - pad), pad, 0, style)

        # A wrapped quote keeps its bar on every row, not just the first
        bar = wrapped.bar_at(y + self.scroll_offset.y)

        if bar is not None:
            bar_style = style + self._theme.syntax_styles.get(QUOTE_BAR, Style())
            glyph = Strip([Segment(QUOTE_GLYPH.rstrip(), bar_style)])
            body = Strip.join(
                [body.crop(0, bar), glyph, body.crop(bar + glyph.cell_length)]
            )

        return Strip.join([gutter, body]) if gutter else body

    def _draw_block(self, strip: Strip, block: str) -> Strip:
        """A heading or a rule, across the whole width of the window, on one row."""

        gutter_width = self.gutter_width
        width = self.scrollable_content_region.width - gutter_width

        if gutter_width:
            gutter, body = strip.divide([gutter_width, strip.cell_length])
        else:
            gutter, body = None, strip

        if block == RULE_SPAN:
            trailing = list(body)[-1].style if body.cell_length else None
            background = Style(bgcolor=trailing.bgcolor) if trailing else Style()
            style = background + self._theme.syntax_styles.get(RULE_SPAN, Style())
            body = Strip([Segment(RULE * width, style)])
        else:
            # A long title is cut at the window's edge, keeping it to one row
            body = body.crop_extend(0, width, None)

        return Strip.join([gutter, body]) if gutter else body

    def _stored_line(self, row: int) -> str:
        """
        Return `row` as stored (markup/link addresses intact), not folded/rendered text.
        """

        document = self.document
        stored_line = getattr(document, "stored_line", None)

        return stored_line(row) if stored_line else document[row]

    def _build_highlight_map(self) -> None:
        """
        Rebuild render_line's highlight map via scan_note (no tree-sitter parser exists for this markup).
        """

        self._line_cache.clear()
        highlights = self._highlights
        highlights.clear()

        document = self.document
        lines = getattr(document, "stored_lines", document.lines)

        raw_rows = getattr(document, "raw_rows", ())

        for row, spans in enumerate(scan_note(lines, raw_rows)):
            highlights[row].extend(spans)
