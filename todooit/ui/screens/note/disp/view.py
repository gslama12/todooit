"""
The text area a note is drawn in: folded markup, hanging lines, quote bars
"""

from dataclasses import dataclass
from typing import Optional, Sequence, Tuple

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
    BACKDROP,
    MARKED,
    MARKED_FIRST,
    QUOTE_BAR,
    QUOTE_GLYPH,
    RULE,
    RULE_SPAN,
    TARGET,
    heading_span,
    scan_note,
)

# (row, start column, end column, style name), in stored columns
OverlaySpan = Tuple[int, int, int, str]

# (row, column, text, style name), a drawn column: put over the cells from there,
# past the line's end if need be
OverlayLabel = Tuple[int, int, str, str]


@dataclass(frozen=True)
class Overlay:
    """Something drawn over the note for a moment, whatever it's there for."""

    # Rows dimmed from edge to edge
    dimmed_rows: range

    # Later ones go over earlier ones, and text folded off the page isn't drawn
    # at all.
    spans: Sequence[OverlaySpan]

    labels: Sequence[OverlayLabel] = ()


# What still shows on a row put aside
KEPT_WHEN_DIMMED = (TARGET, MARKED, MARKED_FIRST)


class NoteView(TextArea):
    """A TextArea that draws the note's markup instead of showing it raw."""

    overlay: Optional[Overlay] = None

    def show_overlay(self, overlay: Optional[Overlay]) -> None:
        """Draw `overlay` over the note, or none."""

        self.overlay = overlay
        self._build_highlight_map()
        self.refresh()

    def standing_spans(self) -> Sequence[OverlaySpan]:
        """
        Spans drawn under any overlay, for as long as a subclass has some to give.
        Asked again each time the note is redrawn, so they can follow its text.
        """

        return ()

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

        if found and self.overlay and found[0] in self.overlay.dimmed_rows:
            strip = self._dim(strip)
        elif span:
            strip = self._wash(strip, span)

        return self._draw_labels(strip, y)

    def _draw_labels(self, strip: Strip, y: int) -> Strip:
        """Put the overlay's labels over whatever is on this row of the window."""

        if not self.overlay:
            return strip

        for row, column, text, name in self.overlay.labels:
            spot = self.wrapped_document.location_to_offset((row, column))
            x = spot.x + self.gutter_width

            if spot.y == y + self.scroll_offset.y and x < strip.cell_length:
                label = Segment(text, self._theme.syntax_styles[name])
                strip = Strip.join(
                    [
                        strip.crop(0, x),
                        Strip([label]),
                        strip.crop(x + label.cell_length, strip.cell_length),
                    ]
                )

        return strip

    def _dim(self, strip: Strip) -> Strip:
        """
        A whole row put aside, whatever it's made of: nothing on it stands out,
        except for the cursor and what's marked on it.
        """

        base = self._theme.base_style
        cursor = self._theme.cursor_style
        kept = {
            cursor.bgcolor if cursor else None,
            *(self._theme.syntax_styles[name].bgcolor for name in KEPT_WHEN_DIMMED),
        }
        plain = Style(
            color=self._theme.syntax_styles[BACKDROP].color,
            bgcolor=base.bgcolor if base else None,
            bold=False,
            italic=False,
            underline=False,
        )

        return Strip(
            Segment(text, style, control)
            if style is not None and style.bgcolor in kept
            else Segment(text, (style or Style()) + plain, control)
            for text, style, control in strip
        )

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

        overlay_spans = self.overlay.spans if self.overlay else ()

        for row, start, end, name in (*self.standing_spans(), *overlay_spans):
            assert isinstance(document, FoldedDocument)

            drawn = document[row]
            start = document._drawn((row, start))[1]
            end = document._drawn((row, end))[1]

            # The map counts in bytes; an end of 0 would mean the whole line
            if start < end:
                highlights[row].append(
                    (
                        len(drawn[:start].encode()),
                        len(drawn[:end].encode()),
                        name,
                    )
                )
