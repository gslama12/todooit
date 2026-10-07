"""
The note editor widget: modes, markup-as-you-type, clipboard, links
"""

from typing import TYPE_CHECKING, Dict, Optional, Tuple

from rich.style import Style
from textual import events
from textual.binding import Binding
from textual.strip import Strip
from textual.widgets import TextArea
from textual.widgets.text_area import TextAreaTheme

from todooit.api.theme import TodooitThemeBase
from todooit.ui.api.api_components.keys import MotionKeys
from todooit.utils import (
    blend,
    copy_text,
    paste_files,
    paste_text,
)
from todooit.utils.links import (
    EMPH_MARK,
    folded_emph,
    folded_link_at,
)

from .markup import (
    BULLET_MARKS,
    BULLET_SPANS,
    DASHES,
    EMPH,
    EMPH_STAR,
    HEADER,
    HEADER_MARK,
    HEADER_WIDTH,
    INDENT,
    LINK,
    MARKER,
    NO_BRACKETS,
    QUOTE,
    QUOTE_BAR,
    QUOTE_GLYPH,
    QUOTE_ITEM,
    QUOTE_MARK,
    RULE,
    RULE_RE,
    RULE_SPAN,
    bullet_glyph,
    indent_depth,
    item_number,
    line_prefix,
    marker_start,
    pasted_link,
    pasted_paths,
    recount,
    scan_note,
    split_indent,
    split_quote,
    star_pair,
)
from .document import (
    FoldedDocument,
    HangingDocument,
    HangingNavigator,
)

if TYPE_CHECKING:  # pragma: no cover
    from .screen import NoteScreenBase


THEME_NAME = "todooit-note"

# Keyboard mode: NORMAL reads/moves, INSERT types (same names as the status bar).
MODE_NORMAL = "NORMAL"
MODE_INSERT = "INSERT"

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


def build_theme(theme: TodooitThemeBase) -> TextAreaTheme:
    """
    Editor theme painted in the todooit palette rather than TextArea's default
    """

    # One color per nesting level, fading from the accent as depth increases.
    bullet_colors = (
        theme.primary,
        theme.secondary,
        blend(theme.foreground1, theme.background2, 0.35),
    )

    return TextAreaTheme(
        name=THEME_NAME,
        base_style=Style(color=theme.foreground3, bgcolor=theme.background2),
        cursor_style=Style(color=theme.background1, bgcolor=theme.primary),
        # One block of text; a highlighted cursor line would cut it in two.
        cursor_line_style=Style(),
        selection_style=Style(bgcolor=theme.background3),
        syntax_styles={
            # The only emphasis kind; orange since it's otherwise unused here.
            EMPH: Style(color=theme.orange, bold=True),
            # Stray `*` (pasted markdown / unfinished pair): faint, not
            # hidden - invisible at line-start would look like a missing indent.
            MARKER: Style(color=blend(theme.orange, theme.background2, 0.55)),
            # Quoted line drawn like markdown: green text + bar; a marker
            # inside also goes green+bold.
            QUOTE: Style(color=theme.green),
            QUOTE_BAR: Style(color=blend(theme.green, theme.background2, 0.45)),
            QUOTE_ITEM: Style(color=theme.green, bold=True),
            **{
                span: Style(color=color, bold=True)
                for span, color in zip(BULLET_SPANS, bullet_colors)
            },
            # Section break: faint rule + title. No background on the title -
            # would swallow the cursor (primary-on-background1).
            RULE_SPAN: Style(color=blend(theme.foreground1, theme.background2, 0.7)),
            HEADER: Style(color=theme.primary, bold=True),
            # Same underline+italic a link wears on the todo rows.
            LINK: Style(color=theme.primary, underline=True, italic=True),
        },
    )


class NoteEditor(TextArea):
    """
    Plain text editor that styles emphasis, quotes and bullets as typed.

    Two modes: NORMAL (read-only, letters move the cursor) and INSERT (letters
    type). `i` enters INSERT; `escape` steps back to NORMAL, then to the todo.
    Opens in NORMAL when the note has content, INSERT when empty.

    Selecting/copying/pasting work in both modes; cut/paste switch to INSERT.

    Markup is typed like markdown (`- `, `1. `, `> `, `# `, `---`, `*stars*`)
    and rendered on completion. The only keyboard-only action is nesting
    (`tab`/`shift+tab`); a quote wraps a line, so markup nests inside it too.

    Files are attached, not typed: `ctrl+v` drops one in the footer strip;
    `f` focuses it.
    """

    BINDINGS = [
        # Nesting has no markup mark, so it needs a key: `tab` only (ctrl+i is
        # the same byte on non-kitty terminals; no other widget needs it here).
        Binding("tab", "indent", "Indent", show=False),
        Binding("shift+tab", "dedent", "Unindent", show=False),
        # Overrides TextArea's delete-right; clears the whole note (after y/N).
        Binding("ctrl+d,super+d", "clear_note", "Clear the note", show=False),
        # TextArea binds this to cursor_line_start, already on `home`.
        Binding("ctrl+a,super+a", "select_all", "Select all", show=False),
        # TextArea already takes Cmd for cut/copy/undo/redo, but not paste.
        Binding("super+v", "paste", "Paste", show=False),
        # What a Mac's opt/cmd editing chords arrive as through the terminal:
        # opt+delete, shift+opt+arrows, and cmd+backspace (^U).
        Binding("alt+d", "delete_word_right", "Delete word right", show=False),
        Binding("alt+shift+left", "cursor_word_left(True)", show=False),
        Binding("alt+shift+right", "cursor_word_right(True)", show=False),
        # Overrides TextArea's delete-to-line-start: the whole line, as zsh does.
        Binding("ctrl+u", "clear_line", "Clear the line", show=False),
        # Top / bottom of the note (cmd+up/down, sent on by the terminal).
        Binding("ctrl+home", "note_start", "Top of the note", show=False),
        Binding("ctrl+end", "note_end", "Bottom of the note", show=False),
    ]

    def __init__(self, text: str) -> None:
        # read_only is what NORMAL *is*; starts read_only unless there's
        # non-whitespace to read. tab_behavior stays "focus" so escape bubbles.
        super().__init__(text, read_only=bool(text.strip()))

        # Set by the first `g` of a `gg` chord.
        self._pending_g = False

    @property
    def mode(self) -> str:
        return MODE_NORMAL if self.read_only else MODE_INSERT

    def enter_insert(self) -> None:
        if not self.read_only:
            return

        self.read_only = False
        self.note_screen.mode_changed()

    def enter_normal(self) -> None:
        if self.read_only:
            return

        self.read_only = True
        self.note_screen.mode_changed()

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

    def _emph_ending_at(
        self, row: int, column: int
    ) -> Optional[Tuple[int, int]]:
        """
        (start, end) of an emphasised phrase if the cursor sits right at its end, else None - that's where backspace removes the (invisible) marks.
        """

        for start, end in folded_emph(self._stored_line(row)):
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

        cursor_row, column = self.cursor_location

        for at, start, end, marker in recount(self.document.lines, row):
            self.replace(marker, (at, start), (at, end), maintain_selection_offset=False)

            if at == cursor_row and column >= end:
                column += len(marker) - (end - start)

        self.move_cursor((cursor_row, column))

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

    def action_copy(self) -> None:
        """
        Copy the selection, or the whole note if none (overrides TextArea, which does nothing without a selection).
        """

        copy_text(self.app, self.selected_text or self.text)

    def action_paste(self) -> None:
        """
        Drop the system clipboard in at the cursor (overrides TextArea, which only reads its own internal clipboard). Switches to INSERT, since pasting is an edit.
        """

        text = paste_text(self.app)

        # A file-manager copy puts nothing on the text clipboard, so check paste_files() too.
        paths = pasted_paths(text) if text else paste_files()

        if paths:
            # Files are attached to the note, not written into it.
            self.note_screen.attach(paths)
            return

        if not text:
            return

        self.enter_insert()

        if self._paste_as_link(text):
            return

        if result := self._replace_via_keyboard(text, *self.selection):
            self.move_cursor(result.end_location)

    def _paste_as_link(self, text: str) -> bool:
        """
        Insert a pasted URL as a markdown link; False if the paste wasn't a bare URL. The current selection, if any, becomes the link's title.
        """

        link = pasted_link(text)

        if link is None:
            return False

        # Collapse to one line; strip brackets, which would close the markdown link early.
        title = " ".join(self.selected_text.split()).translate(NO_BRACKETS)
        markdown = f"[{title}]({link.url})"

        result = self._replace_via_keyboard(markdown, *self.selection)

        if result is None:
            return True

        self.move_cursor(result.end_location)

        return True

    def action_cut(self) -> None:
        """
        Cut the selection to the clipboard (overrides TextArea for the same reason as `copy`); switches to INSERT like `paste`.
        """

        start, _ = self.selection
        removed = self.selected_text or self.document[start[0]]

        self.enter_insert()
        super().action_cut()

        copy_text(self.app, removed)

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

    @property
    def note_screen(self) -> "NoteScreenBase":
        screen = self.screen

        from .screen import NoteScreenBase

        assert isinstance(screen, NoteScreenBase)
        return screen

    def action_clear_note(self) -> None:
        """
        Ask to clear the whole note; the screen handles the confirmation.
        """

        self.note_screen.request_clear()

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
            self.note_screen.pick_files()
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
        link = folded_link_at(self._stored_line(row), column)

        if link is None:
            self.note_screen.report("No link under the cursor")
            return

        self.note_screen.open_link(link.url)

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

    async def _on_key(self, event: events.Key) -> None:
        """
        Handle mode-specific keys, and carry the bullet/quote prefix onto a newly opened line.
        """

        if self.note_screen.awaiting_answer:
            # Editor keeps focus during a pending question; answer lands here, not on a screen binding.
            event.stop()
            event.prevent_default()
            self.note_screen.answer(event.key)
            return

        # Resolved character, not raw key name, so motions on ö etc. match the trees.
        key = self.note_screen.resolve_key(event)

        if self.read_only:
            if self._handle_normal_key(key):
                event.stop()
                event.prevent_default()

                # Restart the blink so a move mid-blink isn't hidden.
                self._restart_blink()

            # escape bubbles: with no mode left to leave, it should close the window.
            return

        if key == "escape":
            event.stop()
            event.prevent_default()
            self.enter_normal()
            return

        # A Meta chord (`alt+d`) carries its letter, which TextArea would type;
        # skip that so the key reaches its binding instead.
        if key != event.character and key.startswith("alt+"):
            event.prevent_default()
            return

        if event.key == "enter":
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
                event.stop()
                event.prevent_default()

                if below + 1 >= self.document.line_count:
                    self.insert(
                        "\n",
                        (below, len(self.document[below])),
                        maintain_selection_offset=False,
                    )

                self.move_cursor((below + 1, 0))
                return

            prefix = line_prefix(line)

            if prefix:
                event.stop()
                event.prevent_default()

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

                return

        if event.key == "backspace" and self.selection.is_empty:
            row, column = self.cursor_location
            pair = self._emph_ending_at(row, column)

            if pair is not None:
                # Cursor sits right after an emphasis's closing mark: backspace
                # removes the emphasis instead of eating the last letter (marks are invisible).
                event.stop()
                event.prevent_default()
                self._take_emph_off(row, column, pair)
                return

            line = self.document[row]
            _, body = split_quote(line)
            _, bullet, _ = split_indent(body)

            if bullet and 0 < column <= len(line_prefix(line)):
                # In the marker/indent: dedent one level (like enter on an
                # empty item), rather than bite a glyph in half or eat the indent space by space.
                event.stop()
                event.prevent_default()

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

                return

        if event.character == EMPH_STAR and self.selection.is_empty:
            row, column = self.cursor_location
            opening = star_pair(self.document[row], column)

            # Closing star of a finished pair: swap both for zero-width emphasis marks.
            if opening is not None:
                event.stop()
                event.prevent_default()

                # One rewrite of the whole `*phrase*`: the opening star takes a
                # column the mark doesn't, so a separate second edit would land one column off.
                phrase = self.document[row][opening + 1 : column]

                self.replace(
                    EMPH_MARK + phrase + EMPH_MARK,
                    (row, opening),
                    (row, column),
                    maintain_selection_offset=False,
                )

                # Land past the closing mark, outside the emphasis.
                self.move_cursor((row, opening + len(phrase)))
                return

        if event.character == DASHES[0]:
            row, column = self.cursor_location

            # Third dash of a `---` alone on the line: swap for the rule immediately.
            if self.document[row] == DASHES and column == len(DASHES):
                event.stop()
                event.prevent_default()
                self._draw_separator(row)
                return

        if event.character == " ":
            row, column = self.cursor_location
            line = self.document[row]

            # Check the quote bar first, so a mark after it opens inside the quote (not a literal hyphen).
            bar, body = split_quote(line)
            indent = body[: len(body) - len(body.lstrip(" \t"))]

            # Space of `> `, `- `, `* ` or `# `: only bar/indent may precede it and nothing may follow.
            mark = body[len(indent) :] if column == len(line) else ""

            # Text before the cursor, so a `#` in front of existing words still opens a header.
            head = body[len(indent) : max(0, column - len(bar))]

            glyph = None

            # Headers and quotes are whole-line constructs, meaningless nested in another quote.
            if not bar:
                if head and set(head) == {HEADER_MARK}:
                    event.stop()
                    event.prevent_default()
                    self._draw_header(row, column)
                    return

                # Judged on the text before the cursor too, so `> ` in front of existing words quotes them.
                if head == QUOTE_MARK:
                    glyph = QUOTE_GLYPH

            if glyph is None and mark in BULLET_MARKS:
                glyph = bullet_glyph(indent_depth(indent))

            if glyph is not None:
                event.stop()
                event.prevent_default()

                at = len(bar) + len(indent)

                self.replace(
                    glyph, (row, at), (row, column),
                    maintain_selection_offset=False,
                )
                self.move_cursor((row, at + len(glyph)))
                return

        await super()._on_key(event)
