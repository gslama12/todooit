import re
from typing import Callable, Iterator, List, Optional, Tuple

from pathlib import Path

from rich.cells import cell_len
from rich.markup import escape
from rich.style import Style
from rich.text import Text
from textual import events, on
from textual.app import ComposeResult
from textual.binding import Binding
from textual.timer import Timer
from textual.document._document import Document, EditResult
from textual.document._document_navigator import DocumentNavigator
from textual.document._wrapped_document import WrappedDocument
from textual.containers import Vertical
from textual.widgets import Static, TextArea
from textual.widgets.text_area import TextAreaTheme

from todooit.api import Todo
from todooit.api.theme import DooitThemeBase
from todooit.utils import (
    Opened,
    blend,
    copy_text,
    file_icon,
    find_links,
    fold_links,
    link_label,
    looks_like_path,
    open_path,
    open_url,
    paste_files,
    paste_text,
    read_attachments,
    resolve_path,
    write_attachments,
)
from todooit.utils.links import TITLE_MAX as LINK_TITLE_MAX
from todooit.utils.links import (
    EMPH_MARK,
    drawn_column,
    folded_emph,
    folded_link_at,
    mark_pairs,
    stored_range,
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

# What emphasis is delimited by: a zero-width space either side of the words,
# `EMPH_MARK`, which is named over in `utils/links.py` because that is where
# the folding that takes it off the page lives.
#
# A heading needs nothing written on its own line to say it is one, because
# what says so is the rule underneath it - a whole line of its own. Emphasis
# is a phrase inside a line, so something in the line has to say where it
# starts and stops. The way out is a character that is real to the note and
# drawn as nothing at all: the marks are there to be found, deleted and paired
# up, and are folded out of the page the same way the markup of a link is, so
# that no column of the window is ever spent on one and no cursor ever stands
# in one

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


def tidy_marks(text: str) -> str:
    """
    `text` with the emphasis marks that close nothing taken out of it

    A mark is only ever written as half of a finished pair, so a mark with no
    partner is a pair an edit cut in two - a line split down the middle of an
    emphasised phrase, or a phrase deleted out from between its own marks.
    What is left is drawn as nothing, stands in no column and can never be
    paired up again: it is not markup any more, only something the note would
    go on carrying.

    Done on the way out rather than on every keystroke. Nothing upstairs has
    to care that an orphan is there - the fold keeps it off the page and out
    of the cursor's way either way - so the tidying belongs where the note is
    written back, which is also where a note written by an older version of
    all this gets its orphans swept up.
    """

    if EMPH_MARK not in text:
        return text

    lines = []

    for line in text.split("\n"):
        keep = {column for pair in mark_pairs(line) for column in pair}

        lines.append(
            "".join(
                character
                for column, character in enumerate(line)
                if character != EMPH_MARK or column in keep
            )
        )

    return "\n".join(lines)


def scan_markup(
    line: str,
    following: str = "",
    links: Optional[list] = None,
    emph: Optional[list] = None,
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
    note, and an emphasised phrase has lost the marks either side of it.
    `links` and `emph` are where the two of them ended up in what was drawn;
    handed nothing, the scan reads what it can off the line itself, which is
    right for any line that is drawn as it stands.
    """

    def byte(index: int) -> int:
        return len(line[:index].encode("utf-8"))

    links = links if links is not None else find_links(line)
    emph = emph if emph is not None else folded_emph(line)

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

    # Emphasis written the way the note writes it: the marks are already off
    # the page, so what is left to do is light the words that were between
    # them. There is nothing to draw a marker over - that is the whole point
    # of the marks costing no columns
    for start, end in emph:
        yield byte(start), byte(end), EMPH

    # And emphasis written with stars, which is how it arrives from somewhere
    # that speaks markdown and how it looks on the way to being typed: the
    # stars are real characters on the page, so the words go first and the two
    # of them over the top, the spans being applied in the order handed over
    for match in EMPH_RE.finditer(line):
        if match.group("star") is None:
            continue

        start, end = match.span()

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
    lit = []

    for line in lines:
        text, links = fold_links(line)

        drawn.append(text)
        found.append(links)
        lit.append(folded_emph(line))

    for row, line in enumerate(drawn):
        following = drawn[row + 1] if row + 1 < len(drawn) else ""

        yield list(scan_markup(line, following, found[row], lit[row]))


# What a name for a link may not hold, since the brackets are what say where
# the name stops
_NO_BRACKETS = str.maketrans("", "", "[]")


def pasted_paths(text: str) -> list:
    """
    The paths a paste is, when the whole of it is nothing else; [] otherwise

    One per line, which is how a file manager writes a copied path out and how
    several of them arrive at once. A single line that is not a path is text
    and goes in as text, and so is a paragraph with a path inside it: the
    whole of what was pasted has to be paths for the paste to mean files.
    """

    lines = [line.strip().strip("\"'").strip() for line in text.splitlines()]
    lines = [line for line in lines if line]

    if not lines or not all(looks_like_path(line) for line in lines):
        return []

    return lines


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

    Files are the one thing here that is never typed. A file copied in a file
    manager - or a path copied as text - is attached by `ctrl+v` and lands in
    the strip along the foot of the window rather than at the cursor, and `f`
    hands the keyboard down to it. Nothing about them is in the text: what is
    written here is what the task says, and what is down there is what it has.
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

    def _emph_ending_at(
        self, row: int, column: int
    ) -> Optional[Tuple[int, int]]:
        """
        The columns an emphasised phrase is drawn between, when the cursor is
        standing at the end of one; None anywhere else

        Read off the same fold that draws the emphasis, so the phrase taken
        out is exactly the phrase that was being drawn.

        The end and nowhere else, because the end is where a backspace is
        aimed: the marks cannot be seen, so the key that comes off them has to
        be the one already being pressed to delete the last letter.
        """

        for start, end in folded_emph(self._stored_line(row)):
            if column == end:
                return start, end

        return None

    def _take_emph_off(self, row: int, column: int, pair: Tuple[int, int]) -> None:
        """
        Take both marks of `pair` out, and leave the words where they were

        Written as one rewrite of the phrase rather than two deletions of a
        mark: the marks are folded off the page, so there is no column of the
        page to delete them at. What there is, is a run of the page whose
        stored form carries them - and putting the drawn words back over that
        run is exactly the emphasis coming off.
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
        Whether the list item on `row` has a level above it to step back out to

        Read off the indent rather than off the glyph, since the indent is
        what a level *is*; the glyph only says so as well. A quoted item
        nests inside its bar, so what is measured is what comes after it.
        """

        _, body = split_quote(self.document[row])
        indent, bullet, _ = split_indent(body)

        return bool(bullet) and indent_depth(indent) > 0

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

        # A file copied in a file manager puts nothing on the text clipboard
        # at all, so an empty one is not an empty clipboard - it is the one
        # case worth asking the desktop a second question about
        paths = pasted_paths(text) if text else paste_files()

        if paths:
            # Not into the text: a file is attached to the note rather than
            # written into it, so the strip is where a pasted one lands and
            # the note goes on saying exactly what it said
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

        if self.note_screen.awaiting_answer:
            # The editor keeps the keyboard while the question stands, so the
            # answer arrives here rather than at a binding on the screen - and
            # is swallowed either way, so a `y` is an answer and not a letter
            event.stop()
            event.prevent_default()
            self.note_screen.answer(event.key)
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
                elif self._nested_item(row):
                    # An empty item nested under another is not the end of the
                    # list but the end of the branch: `enter` walks it back out
                    # one level, which is the way back up a list and the thing
                    # the key is reached for far more often than throwing the
                    # item away. Unwinding the levels one at a time means the
                    # marker still goes in the end - on the `enter` pressed at
                    # the top level, where there is nothing left to climb to
                    self._set_depth(row, -1)
                else:
                    # An empty item at the top level is where the list ends:
                    # the marker goes, rather than another one arriving
                    # underneath it. It goes one marker at a time, so an empty
                    # bullet inside a quote leaves the bar standing and the
                    # quote ends on the next `enter`, the way an unquoted one
                    # ends on the first
                    self.replace("", (row, glyph_at), (row, len(line)))
                    self.move_cursor((row, glyph_at))

                return

        if event.key == "backspace" and self.selection.is_empty:
            row, column = self.cursor_location
            pair = self._emph_ending_at(row, column)

            if pair is not None:
                # Standing just past an emphasised phrase, where the mark that
                # closes it is - and where a backspace would otherwise reach
                # over it to the last letter of the word, leaving the phrase a
                # letter shorter and still emphasised. The marks cannot be
                # seen, so the key has to mean the thing that can: the
                # emphasis comes off, and the words stay
                event.stop()
                event.prevent_default()
                self._take_emph_off(row, column, pair)
                return

            line = self.document[row]
            _, body = split_quote(line)
            _, bullet, _ = split_indent(body)

            if bullet and 0 < column <= len(line_prefix(line)):
                # Anywhere in the marker or the indent in front of it - which
                # is where a backspace would otherwise bite a glyph in half or
                # take a level's worth of indent one space at a time. What the
                # key means here is the same thing `enter` on an empty item
                # means: a level back out, one at a time, with the words coming
                # along - and the marker itself only going at the top, where
                # there is no level left to step back to
                event.stop()
                event.prevent_default()

                if self._nested_item(row):
                    self._set_depth(row, -1)
                else:
                    # The marker goes and the words stay where they start: a
                    # quoted item leaves its bar standing, so the bullet comes
                    # off first and the quote ends on the next backspace, the
                    # way it ends on the next `enter`
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

            # The star that closes a pair, swapped along with the one it
            # closes for the marks that cost no columns - the same swap `- `
            # makes into a bullet, and for the same reason: what the note
            # holds is what the window draws. A `*` left standing at the head
            # of a line would read as an indent that is not there
            if opening is not None:
                event.stop()
                event.prevent_default()

                # Written as one rewrite of the whole `*phrase`, because the
                # opening star is a column of the page and the mark that
                # replaces it is not: swapping them one at a time would leave
                # the second half of the edit aimed a column past where the
                # page had just moved to
                phrase = self.document[row][opening + 1 : column]

                self.replace(
                    EMPH_MARK + phrase + EMPH_MARK,
                    (row, opening),
                    (row, column),
                    maintain_selection_offset=False,
                )

                # Past the closing mark, which is where the star was typed and
                # where the next letter belongs: outside the emphasis
                self.move_cursor((row, opening + len(phrase)))
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


# What stands between two files in the strip. One column, because each file is
# already drawn with a space either side of it - the room its background needs
# to read as a thing picked up rather than as words that have gone dark
FILE_GAP = " "

# Nothing about the strip counts, hides or shortens: every file attached to a
# note is drawn on it, and when they stop fitting on a line the strip grows
# another one and goes on. A file nobody can see is a file nobody remembers is
# there, which is the whole of what an attachment is for


class AttachmentStrip(Static):
    """
    The files a note carries, along the foot of the window inside its frame

    Not part of the note. Nothing here is text that can be typed over,
    indented or deleted by accident: the note is what the task *says* and this
    is what it *has*, and the two are kept apart on the page because they are
    kept apart in the database.

    It takes the keyboard while files are being picked through, which is what
    makes the cursor in the text go quiet - two cursors on one window, one of
    them live and one of them left behind, is the thing this avoids - and
    hands it straight back on `escape`.
    """

    DEFAULT_CSS = """
    AttachmentStrip {
        height: auto;
        display: none;
    }
    """

    can_focus = True

    def __init__(self) -> None:
        super().__init__(id="note-files")

        self.paths: List[Path] = []
        self.picked = 0

        # Which files are drawn on which row, worked out from how wide the
        # window is; one empty row until there is something to put on it
        self.rows: List[List[int]] = [[]]

    @property
    def has_the_keyboard(self) -> bool:
        """
        Whether the keys are landing here rather than up in the text

        Read off the screen rather than off `has_focus`, which is a reactive
        and is still catching up while the `Focus` event that sets it is being
        handled - which is exactly when this is asked
        """

        screen = self.note_screen

        return screen is not None and screen.focused is self

    @property
    def current(self) -> Optional[Path]:
        """
        The file the strip is standing on, if it is standing on one
        """

        if not self.paths or not 0 <= self.picked < len(self.paths):
            return None

        return self.paths[self.picked]

    def show(self, paths, theme: DooitThemeBase) -> None:
        """
        Draw the strip, and take it off the page when there is nothing on it
        """

        self.paths = list(paths)
        self.picked = max(0, min(self.picked, len(self.paths) - 1))
        self.display = bool(self.paths)

        if self.paths:
            self.rows = self._rows()
            self.update(self._drawn(theme))

    def _label(self, path: Path) -> str:
        """
        One file as it is written on the page: what it is, and what it is
        called, with a space either side for the background to sit in
        """

        return f" {file_icon(path.name)} {path.name} "

    def _rows(self) -> List[List[int]]:
        """
        The files dealt out into the rows they are drawn on

        As many as fit on a line, then the next line, for as many lines as it
        takes. Nothing is ever left off: the strip grows up into the note
        instead. The one thing that is ever shortened is a name too long for a
        line of its own, and only as far as the line - the file is still
        listed, and it is still the one the keys open.
        """

        room = self.size.width or 0
        rows: List[List[int]] = [[]]
        used = 0

        for index, path in enumerate(self.paths):
            width = cell_len(self._label(path))
            gap = cell_len(FILE_GAP) if rows[-1] else 0

            if room and rows[-1] and used + gap + width > room:
                rows.append([])
                used = 0
                gap = 0

            rows[-1].append(index)
            used += gap + width

        return rows

    def _drawn(self, theme: DooitThemeBase) -> Text:
        """
        The strip as it is painted, row by row, the picked one lit

        Quiet by default and quieter still when the keyboard is elsewhere: a
        strip that is not being picked through is a caption under the note,
        and a caption that shouts is a caption in the way.
        """

        quiet = Style(color=blend(theme.foreground3, theme.background1, 0.25))
        icon = Style(color=blend(theme.secondary, theme.background1, 0.35))
        lit = Style(color=theme.primary, bgcolor=theme.background3, bold=True)

        drawn = Text(no_wrap=True, overflow="ellipsis")

        for row, indexes in enumerate(self.rows):
            if row:
                drawn.append("\n")

            for place, index in enumerate(indexes):
                chip = Text(self._label(self.paths[index]))

                if self.has_the_keyboard and index == self.picked:
                    chip.stylize(lit)
                else:
                    chip.stylize(quiet)
                    chip.stylize(icon, 0, 3)

                if place:
                    drawn.append(FILE_GAP)

                drawn.append_text(chip)

        return drawn

    def row_of(self, index: int) -> int:
        """
        Which row a file is drawn on
        """

        for row, indexes in enumerate(self.rows):
            if index in indexes:
                return row

        return 0

    def step_row(self, step: int) -> bool:
        """
        Move to the file above or below this one; False when there is none

        The same place along the row, as near as the row below has one - which
        is what moving down a list of things does everywhere else.
        """

        row = self.row_of(self.picked)
        place = self.rows[row].index(self.picked)
        target = row + step

        if not 0 <= target < len(self.rows):
            return False

        indexes = self.rows[target]
        self.picked = indexes[min(place, len(indexes) - 1)]

        return True

    def on_resize(self) -> None:
        """
        A narrower window deals the same files out over more rows
        """

        self.refresh_strip()

    def on_focus(self) -> None:
        self.keyboard_moved()

    def on_blur(self) -> None:
        self.keyboard_moved()

    def keyboard_moved(self) -> None:
        """
        Redraw, and have the window say what the keys down here do

        Hung off the focus events rather than off whatever asked for the
        focus, because asking is not the same as having it: the window says
        what it is doing once it is doing it.
        """

        screen = self.note_screen

        if screen is None:
            return

        self.refresh_strip()
        screen.mode_changed()

    @property
    def note_screen(self) -> Optional["NoteScreenBase"]:
        """
        The window this is in, or None on the way off the page
        """

        try:
            screen = self.screen
        except Exception:
            return None

        return screen if isinstance(screen, NoteScreenBase) else None

    def refresh_strip(self) -> None:
        screen = self.note_screen

        if screen is not None:
            self.show(self.paths, screen.api.vars.theme)

    async def _on_key(self, event: events.Key) -> None:
        """
        The keys of the strip, which are the keys a list of things answers to

        Everything is swallowed rather than let past: while the strip has the
        keyboard, a letter is a key here or it is nothing at all - the note
        underneath is being read, not typed in.
        """

        event.stop()
        event.prevent_default()

        screen = self.screen
        assert isinstance(screen, NoteScreenBase)

        if screen.awaiting_answer:
            screen.answer(event.key)
            return

        screen.file_key(screen.resolve_key(event))


class NoteFrame(Vertical):
    """
    The window itself: the text, and the files along the bottom of it

    The border, the title and the mode chip are drawn here rather than on the
    editor, because there are two things inside the frame now and both of them
    belong to the note. What that buys is that the strip is *inside* the
    window: a file picked out is lit on the note's own background, where the
    eye is already looking, rather than on a patch of the screen behind it.
    """

    DEFAULT_CSS = """
    NoteFrame {
        & > NoteEditor {
            height: 1fr;
        }
    }
    """


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

        & > NoteFrame {
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
            "i insert    jklö move    o link    f files    "
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

    # And the line for the strip, which is a third thing the window can be
    # doing: the keys down there are not the keys up in the text
    FILES_HINT = "jö/kl pick    enter open    xx detach    esc back to the note"

    # Worded and escaped the way the confirm bar words a deletion elsewhere in
    # dooit, so the answer is the one the user already knows
    CLEAR_PROMPT = r"Clear the whole note? \[y/N]"

    # The other thing a note has to ask about. A file that has been moved or
    # thrown away is an entry that will never open again, and the moment that
    # is found out is the moment worth offering to tidy it
    GONE_PROMPT = r"{name} is gone. Detach it? \[y/N]"

    def __init__(self) -> None:
        super().__init__()
        self._save_timer: Optional[Timer] = None
        self._report_timer: Optional[Timer] = None

        # What a `y` would do, and the whole of what says a question is up
        self._question: Optional[Callable[[], None]] = None

        # Raised by the first `x` of an `xx` down in the strip
        self._pending_x = False

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
    def frame(self) -> NoteFrame:
        return self.query_one(NoteFrame)

    @property
    def editor(self) -> NoteEditor:
        return self.query_one(NoteEditor)

    @property
    def hint(self) -> Static:
        return self.query_one("#note-hint", Static)

    @property
    def awaiting_answer(self) -> bool:
        return self._question is not None

    def load_attachments(self) -> str:
        """
        The files this note carries, as they are stored: one path per line
        """

        raise NotImplementedError  # pragma: no cover

    def store_attachments(self, text: str) -> None:
        """
        Write them back. Unlike the text, this is not on a debounce: attaching
        and detaching are whole gestures rather than a stream of keystrokes
        """

        raise NotImplementedError  # pragma: no cover

    @property
    def files(self) -> AttachmentStrip:
        return self.query_one(AttachmentStrip)

    @property
    def picking_files(self) -> bool:
        return self.files.has_the_keyboard

    def compose(self) -> ComposeResult:
        editor = NoteEditor(self.load_note())

        frame = NoteFrame()
        frame.border_title = self.title_text

        with frame:
            yield editor
            yield AttachmentStrip()

        yield Static(self.HINTS[editor.mode], id="note-hint")

    def on_mount(self) -> None:
        editor = self.editor
        editor.register_theme(build_theme(self.api.vars.theme))
        editor.theme = THEME_NAME

        self.files.show(read_attachments(self.load_attachments()), self.api.vars.theme)

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

        frame = self.frame

        frame.border_subtitle = f" {mode} "
        frame.set_class(mode == MODE_INSERT, "-insert")

        # A question standing in the hint line outranks the hints themselves;
        # answering it puts the right ones back
        if not self.awaiting_answer:
            self.hint.update(
                self.FILES_HINT if self.picking_files else self.HINTS[mode]
            )

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

    # ------------------------------------------------------------------
    # ------------------------- The files ------------------------------
    # ------------------------------------------------------------------

    def attach(self, paths) -> None:
        """
        Put files in the strip, and say which ones went in

        What is kept is the path. The file is never copied, never moved and
        never looked at: two notes can point at one file, and attaching a film
        costs exactly what attaching a shopping list costs.
        """

        held = list(self.files.paths)
        fresh = []

        for raw in paths:
            path = resolve_path(str(raw))

            if path is None or path in held:
                continue

            held.append(path)
            fresh.append(path)

        if not fresh:
            self.report("Already attached")
            return

        self._write(held)

        # Standing on what just arrived, so the key that opens it is the next
        # one pressed and nothing has to be found first
        self.files.picked = len(held) - 1
        self.report(
            f"Attached {fresh[0].name}"
            if len(fresh) == 1
            else f"Attached {len(fresh)} files"
        )

    def _write(self, paths) -> None:
        """
        Put the list back, on the page and in the database at once
        """

        self.files.show(paths, self.api.vars.theme)
        self.store_attachments(write_attachments(paths))

    def pick_files(self) -> None:
        """
        Hand the keyboard to the strip, where a file can be picked out
        """

        if not self.files.paths:
            self.report("Nothing attached")
            return

        self.files.focus()

    def leave_files(self) -> None:
        """
        Hand it back to the text, exactly where the cursor was left standing
        """

        self.editor.focus()

    def file_key(self, key: str) -> None:
        """
        A key pressed while the strip has the keyboard

        The keys of a list of things, and the same ones the panes behind this
        window use for them: the motions pick one out, `xx` throws one away,
        and `enter` is what you press on the one you meant.
        """

        strip = self.files
        pending_x, self._pending_x = self._pending_x, False

        if key == "x":
            if pending_x:
                self.detach()
            else:
                self._pending_x = True
        elif key in ("j", "b"):
            strip.picked = max(0, strip.picked - 1)
            strip.refresh_strip()
        elif key in ("ö", "w"):
            strip.picked = min(len(strip.paths) - 1, strip.picked + 1)
            strip.refresh_strip()
        elif key == "0":
            strip.picked = 0
            strip.refresh_strip()
        elif key == "$":
            strip.picked = len(strip.paths) - 1
            strip.refresh_strip()
        elif key in ("k", "l"):
            # Up off the top row is the way back into the text, which is where
            # up from the foot of the window means anywhere else
            if strip.step_row(-1 if key == "k" else 1):
                strip.refresh_strip()
            elif key == "k":
                self.leave_files()
        elif key in ("enter", "o"):
            self.open_file()
        elif key in ("escape", "f", "i"):
            self.leave_files()

    def open_file(self) -> None:
        """
        Open the file the strip is standing on, and say how it went

        Nothing about it shows up in here - the application it belongs to
        comes up somewhere else entirely, or nothing does - so the line
        underneath is what says the key landed.
        """

        path = self.files.current

        if path is None:
            return

        outcome = open_path(path)

        if outcome is Opened.OK:
            self.report(f"Opening {path.name}")
        elif outcome is Opened.MISSING:
            self.ask(self.GONE_PROMPT.format(name=escape(path.name)), self.detach)
        else:
            self.report("Found nothing to open it with")

    def detach(self) -> None:
        """
        Take the file the strip is standing on off the note

        No question and no undoing it: an attachment is a way back to
        something, and nothing is lost with it but the way back. The file
        itself is not touched - it never was ours.
        """

        path = self.files.current

        if path is None:
            return

        kept = [held for held in self.files.paths if held != path]

        self._write(kept)
        self.report(f"Detached {path.name}")

        if not kept:
            self.leave_files()

    @on(TextArea.Changed)
    def schedule_save(self, _: TextArea.Changed) -> None:
        if self._save_timer is not None:
            self._save_timer.stop()

        self._save_timer = self.set_timer(SAVE_DEBOUNCE, self.save)

    def save(self) -> None:
        self._save_timer = None
        self.store_note(tidy_marks(self.editor.text))

    def ask(self, prompt: str, answered: Callable[[], None]) -> None:
        """
        Put a question up, in place of the hint line

        One question at a time, and the next keystroke is its answer: the
        window keeps the keyboard while it stands, so there is nowhere for a
        second one to be put and nothing to do with it if there were.
        """

        if self.awaiting_answer:
            return

        self._question = answered
        self.hint.update(prompt)
        self.hint.add_class("confirming")

    def answer(self, key: str) -> None:
        """
        Anything but a `y` leaves the note exactly where it is
        """

        answered, self._question = self._question, None
        self.hint.remove_class("confirming")
        self.mode_changed()

        if key.lower() == "y" and answered is not None:
            answered()

    def request_clear(self) -> None:
        """
        Offer to throw the whole note away
        """

        # Nothing to lose, nothing to ask about
        if not self.editor.text:
            return

        self.ask(self.CLEAR_PROMPT, self._clear)

    def _clear(self) -> None:
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

    def load_attachments(self) -> str:
        return self.todo.attachments or ""

    def store_attachments(self, text: str) -> None:
        if self.todo.attachments == text:
            return

        self.todo.attachments = text
        self.todo.save()

    def store_note(self, text: str) -> None:
        if self.todo.note == text:
            return

        self.todo.note = text
        self.todo.save()
