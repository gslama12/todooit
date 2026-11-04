"""
The text area a note is drawn in: folded markup, hanging lines, quote bars
"""

from rich.segment import Segment
from rich.style import Style
from textual.strip import Strip
from textual.widgets import TextArea

from .document import (
    FoldedDocument,
    HangingDocument,
    HangingNavigator,
)
from .markup import (
    QUOTE_BAR,
    QUOTE_GLYPH,
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

    def _render_line(self, y: int) -> Strip:
        """
        Render a wrapped continuation row, indented via blank padding columns (not real characters, so line offsets elsewhere are unaffected).
        """

        strip = super()._render_line(y)
        pad = self.wrapped_document.pad_at(y + self.scroll_offset.y)

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
        bar = self.wrapped_document.bar_at(y + self.scroll_offset.y)

        if bar is not None:
            bar_style = style + self._theme.syntax_styles.get(QUOTE_BAR, Style())
            glyph = Strip([Segment(QUOTE_GLYPH.rstrip(), bar_style)])
            body = Strip.join(
                [body.crop(0, bar), glyph, body.crop(bar + glyph.cell_length)]
            )

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

        for row, spans in enumerate(scan_note(lines)):
            highlights[row].extend(spans)
