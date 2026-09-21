import re
from typing import Iterator, Optional, Tuple

from rich.style import Style
from textual import events, on
from textual.app import ComposeResult
from textual.binding import Binding
from textual.timer import Timer
from textual.document._document import Document, EditResult
from textual.document._document_navigator import DocumentNavigator
from textual.document._wrapped_document import WrappedDocument
from textual.widgets import Static, TextArea
from textual.widgets.text_area import TextAreaTheme

from todooit.api import Todo
from todooit.api.theme import DooitThemeBase
from todooit.utils import (
    blend,
    copy_text,
    find_links,
    fold_links,
    link_label,
    open_url,
    paste_text,
)
from todooit.utils.links import TITLE_MAX as LINK_TITLE_MAX
from todooit.utils.links import drawn_column, folded_link_at, stored_range

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

# The two below and the `>` above are all read the same way, and the space
# after them is what says they mean it: a `-` in the middle of a word is a
# hyphen, a `*` is half of an emphasis and a `#` is a number sign. Only a mark
# with nothing but indent in front of it and a space behind it opens a line.

# What a list item is typed as before it becomes the bullet: markdown's own
# `-` and `*`, whichever of the two the fingers reach for. Both arrive as the
# same glyph, because the note draws one kind of bullet - the mark says only
# that a list is being written. Which glyph arrives follows how deep the line
# is already indented, so it is looked up rather than stored here
BULLET_MARKS = ("-", "*")

# The `*` on its own, which is the other thing a star does here: a pair of
# them around a phrase is markdown's emphasis. Which of the two a star means
# is settled by what follows it - a space opens a list, anything else is words
# on the way to being emphasised
EMPH_STAR = "*"

# What a title is typed as before the rule is drawn underneath it: markdown's
# `#`. A run of them opens one too, since every depth of markdown heading
# means heading, and this note has exactly the one to give them all
HEADER_MARK = "#"

# What `---` is typed as before it becomes the rule. Two dashes and a third
# on the way, which is the moment the line is swapped for the rule itself.
# A `-` alone is a bullet on the way instead, and the two never meet: the
# rule is three dashes running, the bullet is one with a space after it
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
QUOTE_ITEM = "note-quote-item"

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

# Either mark. The `*` is what emphasis is *typed* with, being the pair of
# characters markdown has always used for it, but a finished pair is swapped
# for the zero-width marks on the way in, the same way `- ` is swapped for the
# bullet it stands for: a `*` costs a column whatever else is true of it, and
# one at the head of a line reads as an indent that is not there.
#
# The `*` form is still read, for a note pasted in from somewhere that speaks
# markdown or written before the swap - and it is read the way markdown reads
# it, needing something between the two stars with neither of them leaning on
# a space, so that the `a * b * c` of an arithmetic stays arithmetic
EMPH_RE = re.compile(
    rf"{EMPH_MARK}(?P<emph>[^{EMPH_MARK}]+){EMPH_MARK}"
    r"|\*(?P<star>[^*\s](?:[^*]*[^*\s])?)\*"
)

BULLET_RE = re.compile(
    rf"^(?P<indent>[ \t]*)(?P<marker>[{''.join(BULLET_GLYPHS)}] )"
)

# An enumerated item, kept exactly as it was typed. There is no glyph to swap
# the number for - which number it is, is the half of it that matters - so
# unlike a bullet it is only ever colored, and it is colored the same way,
# because a numbered list and a dashed one are one list with two markers
ORDERED_RE = re.compile(r"^(?P<indent>[ \t]*)(?P<marker>\d+\. )")

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
# note is walked with the same fingers as the trees behind it.
#
# Only these, and no vim key beyond them: a letter that is not on this list
# does nothing at all in NORMAL. Word motions were once here on `w` and `b`,
# and the surprise of a letter moving the cursor was not worth the two hops
# they saved
NORMAL_MOTIONS = {
    "j": "cursor_left",
    "ö": "cursor_right",
    "k": "cursor_up",
    "l": "cursor_down",
    "0": "cursor_line_start",
    "$": "cursor_line_end",
}

# The one key that drops into INSERT, at the cursor. vim's other three ways in
# - `a` past the cursor, `I` and `A` at either end of the line - are not here:
# a key that flips the mode out from under the fingers is a key that turns the
# next letter typed into text in the note, which is not what a reader pressing
# letters is after
INSERT_ENTRY = "i"


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


def split_quote(line: str) -> Tuple[str, str]:
    """
    One line as (its quote bar, everything after it), with an empty bar when
    the line is not quoted

    A quote is not a kind of line but a wrapper around one, so this is the
    first thing every reader here does: a bullet inside a quote is a bullet
    that happens to be quoted, and from this call on it is read as one.
    """

    match = QUOTE_RE.match(line)

    return (line[: match.end()], line[match.end() :]) if match else ("", line)


def line_prefix(line: str) -> str:
    """
    What a line opens with before its words start: its quote bar, its indent
    and the bullet after them, or "" when it opens with none of the three

    This is what `enter` carries onto the next line, so that a list goes on
    being a list, a quote goes on being a quote, and a list inside a quote
    goes on being both.
    """

    bar, body = split_quote(line)
    bullet = BULLET_RE.match(body)

    return bar + (body[: bullet.end()] if bullet else "")


def marker_start(line: str) -> int:
    """
    Where the innermost marker of `line` begins - the column an item with
    nothing written on it is unwound from

    A list ends one marker at a time. The bullet of an empty quoted item goes
    first and leaves the bar it was written inside, and the bar goes on the
    next `enter`: so this is where the bullet starts when there is one, and
    where the bar starts when there is not.
    """

    bar, body = split_quote(line)
    bullet = BULLET_RE.match(body)

    if not bullet:
        return 0

    return len(bar) + len(bullet.group("indent"))


def star_pair(line: str, column: int) -> Optional[int]:
    """
    Where the `*` that a star typed at `column` closes is, or None when it
    closes nothing and is only a star

    What markdown asks of a pair is asked here: something between the two
    stars, and neither of them leaning on a space. The second star of
    `a * b * c` closes nothing, and stays the star it was typed as.
    """

    opening = line.rfind(EMPH_STAR, 0, column)

    if opening < 0:
        return None

    inner = line[opening + 1 : column]

    if not inner or inner[0].isspace() or inner[-1].isspace():
        return None

    return opening


def split_indent(line: str) -> Tuple[str, str, str]:
    """
    One line - already past its quote bar, if it had one - as (indent, bullet,
    the rest), with an empty bullet when there is none: the three pieces a
    line is re-indented out of
    """

    match = BULLET_RE.match(line)

    if match:
        return match.group("indent"), match.group("marker"), line[match.end() :]

    stripped = line.lstrip(" \t")
    return line[: len(line) - len(stripped)], "", stripped


def scan_markup(
    line: str,
    following: str = "",
    links: Optional[list] = None,
) -> Iterator[Tuple[int, int, str]]:
    """
    The styled spans of one line, measured in UTF-8 bytes

    `TextArea.render_line` maps the offsets it is handed back through a
    byte-to-codepoint table, so anything counted in characters would land in
    the wrong place on a line holding an umlaut - or a bullet.

    `following` is the line below, which is all a header needs to be
    recognised: the rule is what says the words above it are a title.

    `line` is the line as it is *drawn*, which is not always the line as it is
    stored - a link folded down to its name is shorter on the page than in the
    note. `links` is where the links ended up in what was drawn; handed
    nothing, the scan reads them off the line itself, which is right for any
    line that is drawn as it stands.
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

    bar, body = split_quote(line)

    if bar:
        # The whole line goes green and the bar over the top of it, and then
        # the ordinary scans run on afterwards over what is left: a quoted
        # line is still a line of the note, so a list in one is still a list
        # and a link in one is still underlined and still opens
        yield 0, byte(len(line)), QUOTE
        yield 0, byte(len(bar)), QUOTE_BAR

    # A bullet and a number are one thing here: both are the marker a list
    # item opens with. Outside a quote the color says how deep the item sits;
    # inside one it says the item is quoted, and that outranks depth - so the
    # glyph and the indent are left to say how deep it is, which is what they
    # are for anyway
    item = BULLET_RE.match(body) or ORDERED_RE.match(body)
    if item:
        depth = indent_depth(item.group("indent"))
        span = QUOTE_ITEM if bar else BULLET_SPANS[min(depth, len(BULLET_SPANS) - 1)]

        yield (
            byte(len(bar) + item.start("marker")),
            byte(len(bar) + item.end("marker")),
            span,
        )

    # Drawn the same way the trees draw a link in a description, and read off
    # the same scan the `o` key opens one with: what is underlined here is
    # exactly what standing on it will open
    for link in links:
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

    `lines` are the lines as they are *stored*; the spans handed back are into
    the lines as they are *drawn*, with every link folded down to its name.
    The folding is done here rather than taken on trust, so the spans and the
    text they land on are always the same fold.
    """

    drawn = []
    found = []

    for line in lines:
        text, links = fold_links(line)

        drawn.append(text)
        found.append(links)

    for row, line in enumerate(drawn):
        following = drawn[row + 1] if row + 1 < len(drawn) else ""

        yield list(scan_markup(line, following, found[row]))


# What a name for a link may not hold, since the brackets are what say where
# the name stops
_NO_BRACKETS = str.maketrans("", "", "[]")


def _pasted_link(text: str):
    """
    The address a paste is, when the whole of the paste is one and it is long
    enough to be worth naming; None for anything else

    A sentence with a link in it is text and goes in as text. So does an
    address short enough to read where it stands: wrapping that one in
    brackets would cost a name to write and save no room at all.
    """

    stripped = text.strip()
    links = find_links(stripped)

    if len(links) != 1:
        return None

    link = links[0]

    if link.title or (link.start, link.end) != (0, len(stripped)):
        return None

    return link if len(stripped) > LINK_TITLE_MAX else None


class FoldedDocument(Document):
    """
    The note as it is stored, handed out as the note is drawn

    A TextArea draws exactly the text its document gives it, and the note is
    stored with the whole of every URL written out in it. The two have to
    differ for a long link to fit on the line it was written on, and this is
    the one place they are allowed to.

    Everything above here - the cursor, the wrapping, the styling, every
    range an edit is asked for - is counted in the columns of the page, and
    the page is the folded text. Everything below here is the note as it was
    typed. The translating is done in this class and nowhere else, so nothing
    upstairs has to know that a line is drawn shorter than it is written, and
    the note on disk is never anything but what was typed into it.

    A folded link is one thing on the page. There is no column inside the name
    to put a cursor in, because the name stands in for the whole of
    `[name](url)`, so an edit reaching into a link is widened to take all of
    it. That is what keeps an address from being cut in half by a keystroke
    aimed at the middle of a word that is not really there.
    """

    def _line(self, row: int) -> str:
        """
        One stored line, for a row that may have been clamped out of range
        """

        return self._lines[max(0, min(row, len(self._lines) - 1))]

    @property
    def lines(self) -> list:
        return [fold_links(line)[0] for line in self._lines]

    @property
    def stored_lines(self) -> list:
        """
        The note as it is written, which is what a save writes out
        """

        return self._lines

    def stored_line(self, row: int) -> str:
        """
        One line as it is written, for the rewrites that have to keep the
        markup they are moving about
        """

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
        A run of the page, as the run of the note behind it

        A run inside one line is handed over whole, since which columns of it
        a link wants depends on both ends at once. A run across several is cut
        at the line ends, each piece asked for on its own: the first runs to
        the end of its line and the last from the start of its own, which is
        what they mean on the page.
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

        # The end of the edit goes back out in the columns it came in with:
        # what asked for it will put the cursor there
        return EditResult(self._drawn(result.end_location), result.replaced_text)

    def get_text_range(self, start: tuple, end: tuple) -> str:
        # What is picked out on the page comes back as what is written behind
        # it, so a copied link carries its address and not just its name
        top, bottom = self._stored_span(*sorted((start, end)))

        return super().get_text_range(top, bottom)


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
            # For the `*` of anything pasted in from somewhere that speaks
            # markdown, or written before a finished pair was swapped on the
            # way in. Faint, but not painted out: a `*` costs a column
            # whatever color it is, and one hidden at the head of a line reads
            # as an indent that is not there - which is worse than a marker
            # that can be seen and deleted. The zero-width mark takes no
            # column, so none of this does anything at all to it
            MARKER: Style(color=blend(theme.orange, theme.background2, 0.55)),
            # A quoted line, drawn the way markdown draws one: the text set
            # off in green, and a bar down the left where the `>` was typed.
            # A list marker inside one goes green as well, and bold to stand
            # off the words around it
            QUOTE: Style(color=theme.green),
            QUOTE_BAR: Style(color=blend(theme.green, theme.background2, 0.45)),
            QUOTE_ITEM: Style(color=theme.green, bold=True),
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

    Nothing is formatted from a key. Every piece of markup here is written the
    way markdown writes it - `- ` or `* ` for a bullet, `1. ` for a numbered
    one, `> ` for a quote, `# ` for a title, `---` for a rule, `*stars*` for
    emphasis - and is drawn as what it means the moment it is finished. There
    is one thing left for the keyboard, and it is not formatting but nesting:
    `tab` takes a line a level in, `shift+tab` back out.

    A quote wraps a line rather than replacing it, so everything above goes on
    working inside one: a list written in a quote is a list, nested by the same
    `tab`, and drawn in the quote's own green rather than the list palette,
    because in there the color is already saying something.
    """

    BINDINGS = [
        # The one key the markup needs, because nesting is the one thing about
        # a line that cannot be read off the characters on it: a level in is a
        # level of indent, and there is no mark for "indent me" to type.
        #
        # `tab` and nothing else: `ctrl+i` is the same byte on every terminal
        # that does not speak the kitty protocol, so naming it too would be
        # naming this key twice. Nothing is given up by taking the key: this
        # window holds one focusable widget, so a tab has nowhere to move the
        # focus to anyway
        Binding("tab", "indent", "Indent", show=False),
        Binding("shift+tab", "dedent", "Unindent", show=False),
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

    def _set_document(self, text: str, language) -> None:
        """
        Put a folding document behind the editor in place of a plain one

        Upstream builds the document here and wires the wrapping and the
        navigation onto it, so this is the one place the swap can be made
        without any of them being left pointed at the document it replaced.
        """

        super()._set_document(text, language)

        self.document = FoldedDocument(text)
        self.wrapped_document = WrappedDocument(
            self.document, tab_width=self.indent_width
        )
        self.navigator = DocumentNavigator(self.wrapped_document)

        self._build_highlight_map()
        self._rewrap_and_refresh_virtual_size()
        self.move_cursor((0, 0))

    def _stored_line(self, row: int) -> str:
        """
        One line as the note holds it, markup and addresses and all

        Almost nothing in here wants this - the editor is written in the
        columns of the page, and the page is the folded text - but a rewrite
        that puts a whole line back has to put back what was really on it.
        """

        document = self.document
        stored_line = getattr(document, "stored_line", None)

        return stored_line(row) if stored_line else document[row]

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

        document = self.document
        lines = getattr(document, "stored_lines", document.lines)

        for row, spans in enumerate(scan_note(lines)):
            highlights[row].extend(spans)

    def _emph_pair(self, row: int, column: int) -> Optional[Tuple[int, int]]:
        """
        The columns of the two marks the one left of the cursor is half of, or
        None when there is no mark of a pair there

        Read off the same scan that draws the emphasis, so the pair taken out
        is exactly the pair that was being drawn.
        """

        line = self.document[row]

        if not column or line[column - 1] != EMPH_MARK:
            return None

        for match in EMPH_RE.finditer(line):
            if match.group("emph") is None:
                continue

            start, end = match.span()

            if column - 1 in (start, end - 1):
                return start, end - 1

        return None

    def _take_emph_off(self, row: int, column: int, pair: Tuple[int, int]) -> None:
        """
        Take both marks of `pair` out, and leave the cursor in the words

        The closing one first: taking the opening one out would move it.
        """

        opening, closing = pair

        self.replace(
            "", (row, closing), (row, closing + 1), maintain_selection_offset=False
        )
        self.replace(
            "", (row, opening), (row, opening + 1), maintain_selection_offset=False
        )

        # One mark went from in front of the cursor, or both did
        self.move_cursor((row, column - (2 if column - 1 == closing else 1)))

    def _set_depth(self, row: int, levels: int) -> None:
        """
        Move one line `levels` steps in or out

        The indent is rewritten rather than nudged, so a line typed with three
        spaces in front of it lands on a level instead of staying between two;
        and a bullet is re-glyphed on the way, since the marker is half of what
        says how deep a line sits.

        A quoted line nests inside its bar rather than behind it: the bar stays
        where it is and the indent grows after it, so a list written in a quote
        is still in the quote at every level it reaches.
        """

        # The one rewrite that puts a whole line back the way it found it, so
        # the one that has to read the line as it is *written*: handed the
        # folded text it would write the names of the links back over the
        # addresses behind them, and the addresses would be gone
        line = self._stored_line(row)
        bar, body = split_quote(line)
        indent, bullet, rest = split_indent(body)

        depth = max(0, indent_depth(indent) + levels)
        head = bar + INDENT * depth + (bullet_glyph(depth) if bullet else "")

        if head + rest == line:
            return

        _, column = self.cursor_location
        self.replace(
            head + rest,
            (row, 0),
            (row, len(self.document[row])),
            maintain_selection_offset=False,
        )

        # The cursor keeps its place in the words rather than its column: the
        # point of indenting a line is to move the words, not to leave the
        # cursor standing on a different one of them
        self.move_cursor((row, max(0, column + len(head) - len(bar + indent + bullet))))

    def action_indent(self) -> None:
        """
        Take the current line one level in - which is how a bullet is nested

        Refused in NORMAL rather than dropping into INSERT: `tab` is one
        keystroke with no modifier on it, and a bare key that rewrites the
        note is exactly what NORMAL is for not having. Every other piece of
        markup is typed rather than pressed, so this is the only key the
        question comes up for.
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

    def _title_above(self, row: int) -> bool:
        """
        Whether there are words directly over `row` for it to be the rule of

        This is the whole of what tells a header's rule from a separator, and
        it is read exactly the same way here as it is drawn: a rule with a
        line of text over it closes a title, and one with a blank line - or
        the top of the note - over it is a break in the text.
        """

        return row > 0 and bool(self.document[row - 1].strip())

    def _draw_header(self, row: int) -> None:
        """
        Swap the `#` on `row` for the rule that will close the title over it

        The header is the help window's section break: a title with a rule
        drawn across underneath it. There is nothing to write on the title
        line yet - the `# ` is the whole of what has been typed - so what this
        leaves is the rule, and the cursor on the empty line above it, which
        is where the title is about to be typed. It is drawn as a title from
        its first letter, because the rule saying so is already there.

        Whatever indent the mark was typed at goes with it. By the time it is
        drawn a header is a whole line of the note, the rule under it as wide
        as the window allows, so there is no level for it to sit at.
        """

        self.replace(
            "\n" + self.rule,
            (row, 0),
            (row, len(self.document[row])),
            maintain_selection_offset=False,
        )
        self.move_cursor((row, 0))

    def _draw_separator(self, row: int) -> None:
        """
        Swap the `---` on `row` for the rule it stands for

        A blank line is put above it when there are words directly over it,
        because a rule tight under a line of words is not a separator at all -
        it is a header, and would be drawn as one the moment it was written.
        `# ` is how a header is meant on purpose.
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

        if self._paste_as_link(text):
            return

        if result := self._replace_via_keyboard(text, *self.selection):
            self.move_cursor(result.end_location)

    def _paste_as_link(self, text: str) -> bool:
        """
        Drop a pasted address in folded; False when the paste was not one

        The one paste worth rewriting on the way in. A long URL pasted on its
        own is about to be the longest thing in the note and the least worth
        reading, so what goes in is the markdown for it with the brackets left
        empty, which is drawn as a shortened form of its own address.

        What is picked out at the time is the name: pasting an address over a
        phrase is how the phrase becomes the link, which is what the gesture
        means in every editor that has it - and the only way a link here comes
        by a name that was not read off its own address.
        """

        link = _pasted_link(text)

        if link is None:
            return False

        # Onto one line, and with the brackets taken out of it: a name holding
        # the bracket that ends it would be read back as ending there
        title = " ".join(self.selected_text.split()).translate(_NO_BRACKETS)
        markdown = f"[{title}]({link.url})"

        result = self._replace_via_keyboard(markdown, *self.selection)

        if result is None:
            return True

        self.move_cursor(result.end_location)

        return True

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

        if key == INSERT_ENTRY:
            self.enter_insert()
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
        link = folded_link_at(self._stored_line(row), column)

        if link is None:
            self.note_screen.report("No link under the cursor")
            return

        self.note_screen.open_link(link.url)

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

                glyph_at = marker_start(line)

                if column < len(prefix):
                    # The cursor is still in front of the words, somewhere in
                    # the indent or in the marker itself: what opens here is a
                    # blank line above, with the item moving down whole. A
                    # prefix carried on from here would hand that item a second
                    # marker and cut the one it already wears in half
                    self.insert("\n", (row, 0), maintain_selection_offset=False)
                    self.move_cursor((row + 1, column))
                elif line[len(prefix) :].strip():
                    self.insert("\n" + prefix, maintain_selection_offset=False)
                else:
                    # An empty item is where the list ends: the marker goes,
                    # rather than another one arriving underneath it. It goes
                    # one marker at a time, so an empty bullet inside a quote
                    # leaves the bar standing and the quote ends on the next
                    # `enter`, the way an unquoted one ends on the first
                    self.replace("", (row, glyph_at), (row, len(line)))
                    self.move_cursor((row, glyph_at))

                return

        if event.key == "backspace" and self.selection.is_empty:
            row, column = self.cursor_location
            pair = self._emph_pair(row, column)

            if pair is not None:
                # The marks cannot be seen, so a backspace that took only the
                # one it landed on would look like nothing happening at all
                # and leave the other behind for good. Both go, and what that
                # looks like is the emphasis coming off - which is the one
                # thing anyone reaching for backspace next to a mark can mean
                event.stop()
                event.prevent_default()
                self._take_emph_off(row, column, pair)
                return

        if event.character == EMPH_STAR and self.selection.is_empty:
            row, column = self.cursor_location
            opening = star_pair(self.document[row], column)

            # The star that closes a pair, swapped along with the one it
            # closes for the marks that cost no columns - the same swap `- `
            # makes into a bullet, and for the same reason: what the note
            # holds is what the window draws. A `*` left standing at the head
            # of a line would read as an indent that is not there
            if opening is not None:
                event.stop()
                event.prevent_default()

                self.replace(
                    EMPH_MARK,
                    (row, opening),
                    (row, opening + 1),
                    maintain_selection_offset=False,
                )
                self.insert(
                    EMPH_MARK, (row, column), maintain_selection_offset=False
                )
                self.move_cursor((row, column + 1))
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
            line = self.document[row]

            # Past the quote bar before anything else is read, so that a mark
            # typed inside a quote opens inside it: `- ` after the bar is a
            # bullet in the quote, not a hyphen in its words
            bar, body = split_quote(line)
            indent = body[: len(body) - len(body.lstrip(" \t"))]

            # The space of a markdown `> `, `- `, `* ` or `# `, which is where
            # the mark is known to be one and not a stray angle bracket, a
            # hyphen, a star or a number sign. Nothing but the bar and the
            # indent may stand in front of it and nothing at all behind it,
            # and both are kept, so a mark typed on a line already tabbed in
            # opens at the level it is standing on
            mark = body[len(indent) :] if column == len(line) else ""

            glyph = None

            # The two that are whole lines rather than things inside one, and
            # so have nothing to mean in a quote: a quote inside a quote has
            # no second bar to be drawn with, and a title is a line with a
            # rule under it, which is not a line a quote can hold
            if not bar:
                if mark and set(mark) == {HEADER_MARK}:
                    event.stop()
                    event.prevent_default()
                    self._draw_header(row)
                    return

                if mark == QUOTE_MARK:
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
        # The marks are what is worth advertising here, since none of them is
        # a key to be found by pressing things: the line is the list of what
        # the note answers to. The clipboard keys had to go to make room, and
        # are the ones every other text field in the world already taught.
        #
        # Kept to eighty columns, which is what the window is wide in a
        # terminal of the usual size: a hint line that has to wrap breaks
        # wherever it runs out of room, and where it runs out of room is
        # between a mark and the word saying what it does as often as not
        MODE_INSERT: (
            "- bullet  1. list  > quote  # head  --- rule  *emph*  "
            "tab nest  esc normal"
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
