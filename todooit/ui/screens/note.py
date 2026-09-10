import re
from typing import Iterator, Optional, Tuple

from rich.style import Style
from textual import events, on
from textual.app import ComposeResult
from textual.binding import Binding
from textual.timer import Timer
from textual.widgets import Static, TextArea
from textual.widgets.text_area import TextAreaTheme

from todooit.api import Todo
from todooit.api.theme import DooitThemeBase
from todooit.utils import (
    blend,
    copy_text,
    find_links,
    link_at,
    link_label,
    open_url,
    paste_text,
)

from .base import BaseScreen


# Bullets are stored as the glyph itself rather than a "- " swapped out at
# render time: a TextArea draws exactly the text it holds, so a marker can
# never stand in for a different character without the columns drifting apart.
#
# One glyph per level of nesting, the way a printed list changes its marker
# rather than only moving it right: the glyph is what says how deep a line
# sits when the indent in front of it is too narrow to count by eye. Past the
# last one the deepest glyph is simply reused, since a list that far in is
# read off its indent anyway
BULLET_GLYPHS = ("•", "◦", "▪")

# What one level of nesting is worth. Two columns: wide enough to see, narrow
# enough that a list several levels deep still has room for words
INDENT = "  "

# A header is the help window's section break brought into the note: a title
# with a rule drawn across underneath it. Stored as the glyph for the same
# reason the bullet is, and kept on a line of its own rather than sized to the
# words, so that retyping the title can never leave the rule the wrong length.
#
# The same rule on a line with nothing above it to be a title is a separator:
# a break in ordinary text. One glyph, two meanings, told apart by whether
# there are words directly over it
RULE = "─"

# How wide the rule is drawn, before a narrow window is allowed to shorten it.
# Long enough to read as a divider, short enough not to wrap in a small note
HEADER_WIDTH = 40

# What a quoted line opens with: markdown's `>` drawn as the bar it means.
# Stored as the glyph for the same reason the bullet is, and typed as the `>`
# it stands for - the conversion happens on the way in, so what is kept on
# disk is already what the window draws
QUOTE_GLYPH = "▎ "
QUOTE_MARK = ">"

# What `---` is typed as before it becomes the rule. Two dashes and a third
# on the way, which is the moment the line is swapped for the rule itself
DASHES = "--"

# What the styled spans are tagged with; the theme below maps them to styles
EMPH = "note-emph"
MARKER = "note-marker"
BULLET_SPANS = tuple(f"note-bullet-{depth}" for depth in range(len(BULLET_GLYPHS)))
RULE_SPAN = "note-rule"
HEADER = "note-header"
LINK = "note-link"
QUOTE = "note-quote"
QUOTE_BAR = "note-quote-bar"

# What emphasis is delimited by: a zero-width space either side of the words.
#
# A heading needs nothing written on its own line to say it is one, because
# what says so is the rule underneath it - a whole line of its own. Emphasis
# is a phrase inside a line, so something in the line has to say where it
# starts and stops, and a TextArea draws exactly the text it holds. The way
# out is a character that is real to the document and worth no columns to the
# terminal: the marks are there to be found, deleted and paired up, and take
# up no more room on the page than the rule under a heading takes out of it
EMPH_MARK = "\N{ZERO WIDTH SPACE}"

# Either mark, so that emphasis written before this - or pasted in from
# somewhere that speaks markdown - goes on being emphasis. `ctrl+e` only ever
# writes the zero-width one; the `*` are painted the color of the paper, which
# is the most that can be done for a marker that already costs a column
EMPH_RE = re.compile(
    rf"{EMPH_MARK}(?P<emph>[^{EMPH_MARK}]+){EMPH_MARK}" r"|\*(?P<star>[^*]+)\*"
)

BULLET_RE = re.compile(
    rf"^(?P<indent>[ \t]*)(?P<marker>[{''.join(BULLET_GLYPHS)}] )"
)

QUOTE_RE = re.compile(rf"^(?P<indent>[ \t]*)(?P<marker>{QUOTE_GLYPH})")

# A line that is nothing but rule. Three is the shortest run that reads as one
# on purpose rather than as a stray character
RULE_RE = re.compile(rf"^{RULE}{{3,}}[ \t]*$")

THEME_NAME = "dooit-note"

# How long the editor has to sit still before the note is written back
SAVE_DEBOUNCE = 0.4

# How long a message stands in the hint line before the hints come back
REPORT_TIMEOUT = 3

# How much of the todo's description the window title carries
TITLE_MAX = 60

# What the note is doing with the keyboard. The two names are the ones the
# status bar already uses out on the trees, because they mean the same thing
# here: NORMAL reads and moves around, INSERT types
MODE_NORMAL = "NORMAL"
MODE_INSERT = "INSERT"

# The motions NORMAL mode answers to. The four movement keys are dooit's own
# rather than vim's - `j`/`ö` step left and right, `k`/`l` up and down - so the
# note is walked with the same fingers as the trees behind it
NORMAL_MOTIONS = {
    "j": "cursor_left",
    "ö": "cursor_right",
    "k": "cursor_up",
    "l": "cursor_down",
    "w": "cursor_word_right",
    "b": "cursor_word_left",
    "0": "cursor_line_start",
    "$": "cursor_line_end",
}

# The keys that drop into INSERT, each landing the cursor somewhere different
INSERT_ENTRIES = ("i", "a", "I", "A")


def indent_depth(indent: str) -> int:
    """
    How many levels of nesting a run of leading whitespace is worth

    Tabs are counted as one level each, which is what a tab is for; spaces are
    counted in `INDENT`-wide steps and anything left over is rounded down, so
    a line indented by hand lands on the nearest level rather than nowhere.
    """

    return len(indent.expandtabs(len(INDENT))) // len(INDENT)


def bullet_glyph(depth: int) -> str:
    """
    The marker a bullet at `depth` wears, with the space that follows it
    """

    return BULLET_GLYPHS[min(depth, len(BULLET_GLYPHS) - 1)] + " "


def line_prefix(line: str) -> str:
    """
    What a line opens with before its words start: its indent and the bullet
    or quote glyph after it, or "" when it opens with neither

    This is what `enter` carries onto the next line, so that a list goes on
    being a list and a quote goes on being a quote.
    """

    match = BULLET_RE.match(line) or QUOTE_RE.match(line)

    return line[: match.end()] if match else ""


def split_indent(line: str) -> Tuple[str, str, str]:
    """
    One line as (indent, bullet, the rest), with an empty bullet when there
    is none - the three pieces a line is re-indented out of
    """

    match = BULLET_RE.match(line)

    if match:
        return match.group("indent"), match.group("marker"), line[match.end() :]

    stripped = line.lstrip(" \t")
    return line[: len(line) - len(stripped)], "", stripped


def scan_markup(line: str, following: str = "") -> Iterator[Tuple[int, int, str]]:
    """
    The styled spans of one line, measured in UTF-8 bytes

    `TextArea.render_line` maps the offsets it is handed back through a
    byte-to-codepoint table, so anything counted in characters would land in
    the wrong place on a line holding an umlaut - or a bullet.

    `following` is the line below, which is all a header needs to be
    recognised: the rule is what says the words above it are a title.
    """

    def byte(index: int) -> int:
        return len(line[:index].encode("utf-8"))

    if RULE_RE.match(line):
        yield 0, byte(len(line)), RULE_SPAN
        return

    if RULE_RE.match(following) and line.strip():
        # The whole line is the header, and that is the end of it: a title is
        # already as loud as the window can draw it, so emphasis and bullets
        # inside one would be markers with nothing left to mark
        yield 0, byte(len(line)), HEADER
        return

    quote = QUOTE_RE.match(line)
    if quote:
        # The whole line goes green and the bar over the top of it, and then
        # the ordinary scans run on afterwards: a quoted line is still a line
        # of the note, so a link in one is still underlined and still opens
        yield 0, byte(len(line)), QUOTE
        yield byte(quote.start("marker")), byte(quote.end("marker")), QUOTE_BAR

    bullet = BULLET_RE.match(line)
    if bullet:
        depth = indent_depth(bullet.group("indent"))
        span = BULLET_SPANS[min(depth, len(BULLET_SPANS) - 1)]

        yield byte(bullet.start("marker")), byte(bullet.end("marker")), span

    # Drawn the same way the trees draw a link in a description, and read off
    # the same scan the `o` key opens one with: what is underlined here is
    # exactly what standing on it will open
    for link in find_links(line):
        yield byte(link.start), byte(link.end), LINK

    for match in EMPH_RE.finditer(line):
        start, end = match.span()

        # The words first and the markers over the top: the spans are applied
        # in the order they are handed over
        yield byte(start + 1), byte(end - 1), EMPH
        yield byte(start), byte(start + 1), MARKER
        yield byte(end - 1), byte(end), MARKER


def scan_note(lines) -> Iterator[list]:
    """
    The styled spans of every line of a note, one list per line

    Walks the note as a whole rather than styling each line on its own,
    because the line below is what says whether the one above it is a title.
    """

    for row, line in enumerate(lines):
        following = lines[row + 1] if row + 1 < len(lines) else ""

        yield list(scan_markup(line, following))


def build_theme(theme: DooitThemeBase) -> TextAreaTheme:
    """
    The editor painted in the dooit theme rather than a TextArea default
    """

    # One color per level of nesting, walking away from the accent as the list
    # goes in: the eye finds the top level first, which is the one that says
    # what the list is about
    bullet_colors = (
        theme.primary,
        theme.secondary,
        blend(theme.foreground1, theme.background2, 0.35),
    )

    return TextAreaTheme(
        name=THEME_NAME,
        base_style=Style(color=theme.foreground3, bgcolor=theme.background2),
        cursor_style=Style(color=theme.background1, bgcolor=theme.primary),
        # The window is one block of text; a highlighted line would only cut
        # it in two
        cursor_line_style=Style(),
        selection_style=Style(bgcolor=theme.background3),
        syntax_styles={
            # The one kind of emphasis the note has, and orange because that is
            # the loudest color in the palette that means nothing else in here
            EMPH: Style(color=theme.orange, bold=True),
            # For the `*` of anything written before the mark went zero-width,
            # or pasted in from somewhere that speaks markdown: the paper's own
            # color, which is as close to gone as a marker can get once it has
            # already taken a column. The zero-width mark takes none, so this
            # does nothing at all to it
            MARKER: Style(color=theme.background2),
            # A quoted line, drawn the way markdown draws one: the text set
            # off in green, and a bar down the left where the `>` was typed
            QUOTE: Style(color=theme.green),
            QUOTE_BAR: Style(color=blend(theme.green, theme.background2, 0.45)),
            **{
                span: Style(color=color, bold=True)
                for span, color in zip(BULLET_SPANS, bullet_colors)
            },
            # The two halves of the help window's section break: a faint rule,
            # and the title over it in the accent color.
            #
            # The title deliberately takes no background of its own. The cursor
            # is a block of `primary` with `background1` written into it, so a
            # title wearing those as a chip would swallow the cursor whole -
            # there would be nothing left for it to invert against, and typing
            # a header would happen somewhere the eye could not follow
            RULE_SPAN: Style(color=blend(theme.foreground1, theme.background2, 0.7)),
            HEADER: Style(color=theme.primary, bold=True),
            # The same underlined italic a link wears out on the todo rows,
            # so a URL looks like one thing wherever it is written
            LINK: Style(color=theme.primary, underline=True, italic=True),
        },
    )


class NoteEditor(TextArea):
    """
    A plain text editor that styles emphasis, quotes and bullets as typed

    Two modes, the way the rest of dooit has two. NORMAL is where the letters
    move the cursor about and nothing typed reaches the note, and `i` drops
    into INSERT, where they land in it. `escape` climbs back out one step at a
    time: INSERT to NORMAL, NORMAL to the todo the note is on.

    Which mode the window opens in follows what there is to open on: a note
    with something written in it opens in NORMAL, to be read; an empty one in
    INSERT, since reading a blank page is not what it was opened for.

    Selecting, copying and pasting work the same in either mode - shift with a
    motion picks text out, `ctrl+a` takes the lot, and `ctrl+c`/`ctrl+x`/`ctrl+v`
    do what they do in any other text field. Since the last two are edits, they
    take the note into INSERT rather than being refused there.
    """

    BINDINGS = [
        # Takes the key off TextArea, where it walks the cursor to the end of
        # the line - which `end` and `$` both already do
        Binding("ctrl+e", "toggle_emph", "Emphasis", show=False),
        # `b` for block quote. The key is free because bold is gone from the
        # note, and its old meaning is the nearest thing to this one: both are
        # what you press to make a line stand apart from the ones around it
        Binding("ctrl+b", "toggle_quote", "Quote", show=False),
        Binding("ctrl+l", "toggle_bullet", "Bullet", show=False),
        # `tab` and nothing else: `ctrl+i` is the same byte on every terminal
        # that does not speak the kitty protocol, so naming it too would be
        # naming this key twice. Nothing is given up by taking the key: this
        # window holds one focusable widget, so a tab has nowhere to move the
        # focus to anyway
        Binding("tab", "indent", "Indent", show=False),
        Binding("shift+tab", "dedent", "Unindent", show=False),
        # `ctrl+h` would be the mnemonic, but every terminal that does not
        # speak the kitty protocol sends it as a backspace; `t` for title is
        # the next letter along and is spent on nothing else here
        Binding("ctrl+t", "toggle_header", "Header", show=False),
        # Takes the key off TextArea, where it deletes the character to the
        # right of the cursor; here the whole note goes, after a y/N
        Binding("ctrl+d", "clear_note", "Clear the note", show=False),
        # What the key means in every other text field. TextArea spends it on
        # `cursor_line_start` instead, which `home` already covers
        Binding("ctrl+a", "select_all", "Select all", show=False),
    ]

    def __init__(self, text: str) -> None:
        # `tab_behavior` stays at its default of "focus", which is what lets
        # `escape` bubble up to the screen instead of being swallowed here.
        #
        # `read_only` is what NORMAL mode *is*: keystrokes still move the
        # cursor and pick text out, but none of them reach the document, so
        # the letters are free to mean motions instead of themselves. An empty
        # note has nothing to read, so it starts out of it - and whitespace
        # alone counts as empty, being nothing anyone opened the note to see
        super().__init__(text, read_only=bool(text.strip()))

        # Raised by the first `g` of a `gg` and by nothing else
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

    def _build_highlight_map(self) -> None:
        """
        Fill the map `render_line` styles from, out of our own markers

        Upstream fills it from a tree-sitter query; there is no parser for a
        markup this small, and none installed either, so the scan below stands
        in for one. Everything downstream of the map is left alone.
        """

        self._line_cache.clear()
        highlights = self._highlights
        highlights.clear()

        for row, spans in enumerate(scan_note(self.document.lines)):
            highlights[row].extend(spans)

    def _marks_around(self, start, end) -> Optional[Tuple[tuple, tuple]]:
        """
        Where the emphasis marks either side of `start`..`end` are, if it is
        already emphasised from just outside itself

        The marks take up no room, so they are never what is picked out: a
        selection made by eye stops at the last letter, with the closing mark
        sitting just past it. Toggling has to look one character further out
        than it was handed, or it would wrap what is already wrapped.
        """

        (top, left), (bottom, right) = start, end

        opens = left and self.document[top][left - 1] == EMPH_MARK
        closes = right < len(self.document[bottom]) and (
            self.document[bottom][right] == EMPH_MARK
        )

        if not (opens and closes):
            return None

        return ((top, left - 1), (top, left)), ((bottom, right), (bottom, right + 1))

    def action_toggle_emph(self) -> None:
        """
        Emphasise what is picked out, or take the emphasis away again

        The marks are zero-width, so what this writes is the words going
        orange and nothing else appearing around them - which is the whole of
        why the mark is the character it is.
        """

        # Marking text up is writing it: the note is being edited from here on
        self.enter_insert()

        start, end = sorted(self.selection)
        selected = self.selected_text

        if not selected:
            # Nothing picked out: drop an empty pair in and sit between them,
            # so that what is typed next arrives already emphasised
            row, column = self.cursor_location
            self.insert(EMPH_MARK * 2, (row, column))
            self.move_cursor((row, column + 1))
            return

        if (
            selected.startswith(EMPH_MARK)
            and selected.endswith(EMPH_MARK)
            and len(selected) > 2
        ):
            self.replace(selected[1:-1], start, end)
            return

        marks = self._marks_around(start, end)

        if marks is not None:
            opening, closing = marks

            # The closing one first: taking the opening one out would move it
            self.replace("", *closing, maintain_selection_offset=False)
            self.replace("", *opening, maintain_selection_offset=False)
            return

        self.replace(EMPH_MARK + selected + EMPH_MARK, start, end)

    def _toggle_marker(self, pattern: "re.Pattern", glyph: str) -> None:
        """
        Put `glyph` at the head of the current line, or take it away again

        What a bullet and a quote both are: one glyph in front of the words,
        after whatever indent the line already carries.
        """

        self.enter_insert()

        row, column = self.cursor_location
        line = self.document[row]
        match = pattern.match(line)

        if match:
            marker = match.group("marker")

            self.replace("", (row, match.start("marker")), (row, match.end("marker")))
            self.move_cursor((row, max(match.start("marker"), column - len(marker))))
            return

        indent = line[: len(line) - len(line.lstrip(" \t"))]

        self.insert(glyph, (row, len(indent)))
        self.move_cursor((row, column + len(glyph)))

    def action_toggle_quote(self) -> None:
        """
        Set the current line off as a quote, or take it back out again

        The same thing `> ` does in markdown, and typing that is the other way
        to reach it; this is the key for a line that is already written.
        """

        self._toggle_marker(QUOTE_RE, QUOTE_GLYPH)

    def action_toggle_bullet(self) -> None:
        """
        Put a bullet at the head of the current line, or take it away again

        Which glyph it gets follows how far the line is already indented, so a
        bullet put on a line that has been tabbed in arrives as the marker for
        the level it is actually at.
        """

        row, _ = self.cursor_location
        line = self.document[row]
        indent = line[: len(line) - len(line.lstrip(" \t"))]

        self._toggle_marker(BULLET_RE, bullet_glyph(indent_depth(indent)))

    def _set_depth(self, row: int, levels: int) -> None:
        """
        Move one line `levels` steps in or out

        The indent is rewritten rather than nudged, so a line typed with three
        spaces in front of it lands on a level instead of staying between two;
        and a bullet is re-glyphed on the way, since the marker is half of what
        says how deep a line sits.
        """

        line = self.document[row]
        indent, bullet, rest = split_indent(line)

        depth = max(0, indent_depth(indent) + levels)
        head = INDENT * depth + (bullet_glyph(depth) if bullet else "")

        if head + rest == line:
            return

        _, column = self.cursor_location
        self.replace(
            head + rest, (row, 0), (row, len(line)), maintain_selection_offset=False
        )

        # The cursor keeps its place in the words rather than its column: the
        # point of indenting a line is to move the words, not to leave the
        # cursor standing on a different one of them
        self.move_cursor((row, max(0, column + len(head) - len(indent + bullet))))

    def action_indent(self) -> None:
        """
        Take the current line one level in - which is how a bullet is nested

        Refused in NORMAL rather than dropping into INSERT the way the other
        formatting keys do: `tab` is one keystroke with no modifier on it, and
        a bare key that rewrites the note is exactly what NORMAL is for not
        having.
        """

        if self.read_only:
            return

        row, _ = self.cursor_location
        self._set_depth(row, 1)

    def action_dedent(self) -> None:
        """
        Take the current line one level back out again
        """

        if self.read_only:
            return

        row, _ = self.cursor_location
        self._set_depth(row, -1)

    @property
    def rule(self) -> str:
        """
        A rule as wide as it is allowed to be: `HEADER_WIDTH`, or the window
        when that is narrower, so the divider never wraps onto a second line
        """

        return RULE * max(3, min(HEADER_WIDTH, self.wrap_width or HEADER_WIDTH))

    def _delete_line(self, row: int) -> None:
        """
        Take a whole line out, along with the newline that ends it - or, for
        the last line of the note, the one that starts it, since there is no
        other way to leave the line count one shorter than it was
        """

        if row + 1 < self.document.line_count:
            start, end = (row, 0), (row + 1, 0)
        elif row:
            start, end = (row - 1, len(self.document[row - 1])), (row, len(self.document[row]))
        else:
            start, end = (row, 0), (row, len(self.document[row]))

        self.replace("", start, end, maintain_selection_offset=False)

    def _title_above(self, row: int) -> bool:
        """
        Whether there are words directly over `row` for it to be the rule of

        This is the whole of what tells a header's rule from a separator, and
        it is read exactly the same way here as it is drawn: a rule with a
        line of text over it closes a title, and one with a blank line - or
        the top of the note - over it is a break in the text.
        """

        return row > 0 and bool(self.document[row - 1].strip())

    def _rule_row(self, row: int) -> Optional[int]:
        """
        Where the rule of the header `row` belongs to is, if there is one

        Standing on the rule counts as standing on the header it closes, so
        the key undoes a header from either of the two lines it is made of.
        A separator belongs to no title and is left for its own key.
        """

        if RULE_RE.match(self.document[row]):
            return row if self._title_above(row) else None

        below = row + 1
        closed = (
            self.document[row].strip()
            and below < self.document.line_count
            and RULE_RE.match(self.document[below])
        )

        return below if closed else None

    def action_toggle_header(self) -> None:
        """
        Close the current line off as a section title with a rule, or take the
        rule away again

        The header is the help window's section break: the title, and the rule
        drawn across underneath it. Only the rule is ever added or removed -
        the title is the line that was already there, and goes on being
        ordinary text that can be typed over, marked up and deleted.
        """

        self.enter_insert()

        row, column = self.cursor_location
        rule_row = self._rule_row(row)

        if rule_row is not None:
            self._delete_line(rule_row)

            # Standing on the rule, the title is the line above; standing on
            # the title, it is where it already was
            title = row - 1 if rule_row == row else row
            self.move_cursor((max(title, 0), column if title == row else 0))
            return

        line = self.document[row]
        self.insert("\n" + self.rule, (row, len(line)), maintain_selection_offset=False)
        self.move_cursor((row, column))

    def _draw_separator(self, row: int) -> None:
        """
        Swap the `---` on `row` for the rule it stands for

        A blank line is put above it when there are words directly over it,
        because a rule tight under a line of words is not a separator at all -
        it is a header, and would be drawn as one the moment it was written.
        `ctrl+t` is the key for meaning that.
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
        Copy what is picked out - or, when nothing is, the whole note

        Overrides the TextArea binding, which copies a selection and does
        nothing at all without one; a note is short enough that the whole of
        it is the obvious thing to mean by an unqualified copy.
        """

        copy_text(self.app, self.selected_text or self.text)

    def action_paste(self) -> None:
        """
        Drop the clipboard in at the cursor

        Overrides the TextArea binding, which pastes textual's own clipboard:
        that only ever holds what was copied inside dooit, and the point of
        the key here is to bring text in from somewhere else.

        A paste is an edit, so it takes the note into INSERT rather than being
        turned away in NORMAL: the keys after a paste are the ones that tidy
        up what was pasted.
        """

        text = paste_text(self.app)

        if not text:
            return

        self.enter_insert()

        if result := self._replace_via_keyboard(text, *self.selection):
            self.move_cursor(result.end_location)

    def action_cut(self) -> None:
        """
        Take the selection out and put it on the clipboard

        Overrides the TextArea binding for the same reason `copy` does - so
        the text goes out by both clipboard routes and not just textual's own
        - and, like `paste`, drops into INSERT instead of refusing in NORMAL.
        """

        start, _ = self.selection
        removed = self.selected_text or self.document[start[0]]

        self.enter_insert()
        super().action_cut()

        copy_text(self.app, removed)

    @property
    def note_screen(self) -> "NoteScreenBase":
        screen = self.screen

        assert isinstance(screen, NoteScreenBase)
        return screen

    def action_clear_note(self) -> None:
        """
        Offer to throw the whole note away; the screen puts the question
        """

        self.note_screen.request_clear()

    def _handle_normal_key(self, key: str) -> bool:
        """
        Act on a key pressed in NORMAL mode; True when it was one of ours

        Anything not answered here is handed on untouched, which is what keeps
        the shift-motions and the clipboard keys - all of them bindings - the
        same in both modes.
        """

        # Only the key straight after a `g` can be its second half, so the
        # flag is read and dropped in one go
        pending_g, self._pending_g = self._pending_g, False

        if key == "g":
            if pending_g:
                self.move_cursor((0, 0))
            else:
                self._pending_g = True

            return True

        if motion := NORMAL_MOTIONS.get(key):
            getattr(self, f"action_{motion}")()
            return True

        if key == "G":
            self.move_cursor(self.document.end)
            return True

        if key in INSERT_ENTRIES:
            self._enter_insert_at(key)
            return True

        if key == "o":
            self._open_link_under_cursor()
            return True

        if key == "O":
            self._open_line()
            return True

        return False

    def _open_link_under_cursor(self) -> None:
        """
        Open the link the cursor is standing on, and say so when there is none

        Nothing else: reading a note is not editing it, so the key that opens
        a link never lands the note in INSERT - not even by falling through to
        something that would.
        """

        row, column = self.cursor_location
        link = link_at(self.document[row], column)

        if link is None:
            self.note_screen.report("No link under the cursor")
            return

        self.note_screen.open_link(link.url)

    def _enter_insert_at(self, key: str) -> None:
        """
        vim's four ways in: at the cursor, past it, or at either end of the line
        """

        row, column = self.cursor_location
        line = self.document[row]

        if key == "a":
            self.move_cursor((row, min(column + 1, len(line))))

        elif key == "I":
            # Past the marker rather than in front of it: on a bullet or a
            # quoted line the text starts where the glyph ends
            self.move_cursor((row, len(line_prefix(line))))

        elif key == "A":
            self.move_cursor((row, len(line)))

        self.enter_insert()

    def _open_line(self) -> None:
        """
        Start a line under this one and type on it

        On the shifted key, since the lowercase one is spent on opening links:
        the note is read far more often than a line is started in it, and a
        key that opens a link has to be a key that never writes anything.

        A line opened under a bullet gets a bullet of its own, the same way
        `enter` carries one on: this is how the next item of a list is written.
        A quoted line carries its bar over for the same reason.
        """

        row, _ = self.cursor_location
        line = self.document[row]
        prefix = line_prefix(line)

        self.enter_insert()

        self.move_cursor((row, len(line)))
        self.insert("\n" + prefix, maintain_selection_offset=False)

    async def _on_key(self, event: events.Key) -> None:
        """
        The keys of whichever mode the note is in, and the bullet that a new
        line carries over from the one above it
        """

        if self.note_screen.awaiting_clear:
            # The editor keeps the keyboard while the question stands, so the
            # answer arrives here rather than at a binding on the screen - and
            # is swallowed either way, so a `y` is an answer and not a letter
            event.stop()
            event.prevent_default()
            self.note_screen.answer_clear(event.key)
            return

        # The character rather than the key name, so that a keyboard where the
        # motions sit on `ö` is read the same way the trees read it
        key = self.note_screen.resolve_key(event)

        if self.read_only:
            if self._handle_normal_key(key):
                event.stop()
                event.prevent_default()

                # The cursor is the only thing a motion changes; a blink that
                # happened to be mid-off would hide the move that was just made
                self._restart_blink()

            # `escape` is left to bubble on purpose: with no mode left to drop
            # out of, what it drops out of is the window
            return

        if key == "escape":
            event.stop()
            event.prevent_default()
            self.enter_normal()
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
                # A title and its rule are one thing; `enter` from the end of
                # the title steps over the rule into the section it opens
                # rather than pushing the two of them apart
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

                glyph_at = len(prefix) - len(prefix.lstrip(" \t"))

                if line[len(prefix) :].strip():
                    self.insert("\n" + prefix, maintain_selection_offset=False)
                else:
                    # An empty bullet is where the list ends: the marker goes,
                    # rather than another one arriving underneath it. A quote
                    # with nothing in it ends the same way
                    self.replace("", (row, glyph_at), (row, len(line)))
                    self.move_cursor((row, glyph_at))

                return

        if event.character == DASHES[0]:
            row, column = self.cursor_location

            # The third dash of a `---` on a line of its own. Swapped for the
            # rule the moment it is finished, rather than being left as three
            # dashes that only look like one: what the note holds is what the
            # window draws, here as everywhere else in it
            if self.document[row] == DASHES and column == len(DASHES):
                event.stop()
                event.prevent_default()
                self._draw_separator(row)
                return

        if event.character == " ":
            row, column = self.cursor_location

            # The space of a markdown `> `, which is where the quote is known
            # to be one and not a stray angle bracket
            if self.document[row] == QUOTE_MARK and column == len(QUOTE_MARK):
                event.stop()
                event.prevent_default()

                self.replace(
                    QUOTE_GLYPH, (row, 0), (row, column),
                    maintain_selection_offset=False,
                )
                self.move_cursor((row, len(QUOTE_GLYPH)))
                return

        await super()._on_key(event)


class NoteScreenBase(BaseScreen):
    """
    A note in a window over the whole screen

    Everything about writing one lives here - the two modes, the debounce that
    writes it back, the y/N that throws it away - and the three things that
    differ between one note and another are left to whoever subclasses this:
    what the window is called, where the text is read from, and where it goes.
    """

    DEFAULT_CSS = """
    NoteScreenBase {
        align: center middle;

        & > NoteEditor {
            width: 70%;
            height: 60%;
        }

        & > #note-hint {
            width: 70%;
            padding: 0 2;
        }
    }
    """

    BINDINGS = [
        ("escape", "close", "Close the note"),
    ]

    # One line of hints per mode: the keys that do nothing where you are
    # standing would only be noise
    HINTS = {
        MODE_NORMAL: (
            "i insert    jklö move    o link    gg/G ends    "
            "ctrl+c copy    ctrl+d clear    esc close"
        ),
        # The formatting keys are what is worth advertising here; the
        # clipboard keys had to go to make room for them, and are the ones on
        # the line that every other text field in the world already taught.
        #
        # Kept to eighty columns, which is what the window is wide in a
        # terminal of the usual size: a hint line that has to wrap breaks
        # wherever it runs out of room, and where it runs out of room is
        # between a key and the word saying what it does as often as not
        MODE_INSERT: (
            "ctrl+e emph   ctrl+b quote   ctrl+l bullet   tab nest   "
            "ctrl+t head   esc normal"
        ),
    }

    # Worded and escaped the way the confirm bar words a deletion elsewhere in
    # dooit, so the answer is the one the user already knows
    CLEAR_PROMPT = r"Clear the whole note? \[y/N]"

    def __init__(self) -> None:
        super().__init__()
        self._save_timer: Optional[Timer] = None
        self._report_timer: Optional[Timer] = None
        self._awaiting_clear = False

    @property
    def title_text(self) -> str:
        """
        What the window is called, written into its top border
        """

        raise NotImplementedError  # pragma: no cover

    def load_note(self) -> str:
        """
        The text the window opens on
        """

        raise NotImplementedError  # pragma: no cover

    def store_note(self, text: str) -> None:
        """
        Write the text back to wherever this note is kept

        Called on the debounce and again on the way out, so it is handed the
        same text more than once for every one time it changes: what to do
        about that belongs to whichever store is on the other end of it.
        """

        raise NotImplementedError  # pragma: no cover

    @property
    def editor(self) -> NoteEditor:
        return self.query_one(NoteEditor)

    @property
    def hint(self) -> Static:
        return self.query_one("#note-hint", Static)

    @property
    def awaiting_clear(self) -> bool:
        return self._awaiting_clear

    def compose(self) -> ComposeResult:
        editor = NoteEditor(self.load_note())
        editor.border_title = self.title_text

        yield editor
        yield Static(self.HINTS[editor.mode], id="note-hint")

    def on_mount(self) -> None:
        editor = self.editor
        editor.register_theme(build_theme(self.api.vars.theme))
        editor.theme = THEME_NAME

        # The window takes the keyboard, in whichever of the two modes the
        # editor picked out of the text it was handed
        editor.focus()
        self.mode_changed()

    def mode_changed(self) -> None:
        """
        Redraw the two places the mode is written: the chip in the bottom
        border of the window, and the line of hints under it
        """

        mode = self.editor.mode

        self.editor.border_subtitle = f" {mode} "
        self.editor.set_class(mode == MODE_INSERT, "-insert")

        # A question standing in the hint line outranks the hints themselves;
        # answering it puts the right ones back
        if not self._awaiting_clear:
            self.hint.update(self.HINTS[mode])

    def report(self, message: str) -> None:
        """
        Say something in the hint line, and put the hints back afterwards

        The bar dooit talks through is on the screen underneath this one, so
        a note has to do its own talking - and the line the hints are written
        on is already there for it.
        """

        if self._report_timer is not None:
            self._report_timer.stop()

        self.hint.update(message)
        self._report_timer = self.set_timer(REPORT_TIMEOUT, self.mode_changed)

    def open_link(self, url: str) -> None:
        """
        Hand a URL to the browser, and say which one went

        Nothing about it shows up in here - the browser comes up somewhere
        else entirely, or nothing does - so the line underneath is what says
        the key landed.
        """

        if open_url(url):
            self.report(f"Opening {link_label(url)}")
        else:
            self.report("Found no browser to open the link with")

    @on(TextArea.Changed)
    def schedule_save(self, _: TextArea.Changed) -> None:
        if self._save_timer is not None:
            self._save_timer.stop()

        self._save_timer = self.set_timer(SAVE_DEBOUNCE, self.save)

    def save(self) -> None:
        self._save_timer = None
        self.store_note(self.editor.text)

    def request_clear(self) -> None:
        """
        Put the question up, in place of the hint line
        """

        # Nothing to lose, nothing to ask about
        if not self.editor.text or self._awaiting_clear:
            return

        self._awaiting_clear = True
        self.hint.update(self.CLEAR_PROMPT)
        self.hint.add_class("confirming")

    def answer_clear(self, key: str) -> None:
        """
        Anything but a `y` leaves the note exactly where it is
        """

        self._awaiting_clear = False
        self.hint.remove_class("confirming")
        self.mode_changed()

        if key.lower() != "y":
            return

        self.editor.clear()

        # The debounce would get here on its own; writing it out now means the
        # row behind the window is right the moment the window closes
        self.save()

    def action_close(self) -> None:
        if self._save_timer is not None:
            self._save_timer.stop()

        # Nothing left to write the hints back onto once the window is gone
        if self._report_timer is not None:
            self._report_timer.stop()

        # Written out here as well as on the timer, so the last keystrokes
        # can't be lost inside the debounce window
        self.save()

        # `dismiss`, not `pop_screen`: popping throws the callback the screen
        # was pushed with away without running it, and that callback is what
        # redraws the row - so the note icon would not turn up until dooit was
        # restarted
        self.dismiss()


class NoteScreen(NoteScreenBase):
    """
    The note of one todo
    """

    def __init__(self, todo: Todo) -> None:
        super().__init__()
        self.todo = todo

    @property
    def title_text(self) -> str:
        """
        Whose note this is, so the window is not just a box of text
        """

        description = self.todo.description.strip() or "Note"

        if len(description) > TITLE_MAX:
            description = description[: TITLE_MAX - 1] + "…"

        return description

    def load_note(self) -> str:
        return self.todo.note or ""

    def store_note(self, text: str) -> None:
        if self.todo.note == text:
            return

        self.todo.note = text
        self.todo.save()
