"""
The note's markdown: constants, regexes, pure line parsing and how a line is drawn
"""

import re
from typing import Container, Iterator, List, Optional, Sequence, Tuple

from rich.cells import cell_len

from todooit.utils import fold_links
from todooit.utils.links import (
    HEADING_RE,
    folded_emph,
    star_pairs,
)

# What a bullet is drawn as, off the cursor line. One glyph per nesting level;
# past the last, the deepest glyph is reused.
BULLET_GLYPHS = ("•", "◦", "▪")

# One nesting level, in columns.
INDENT = "  "

# Minimum columns a wrapped continuation line must keep after its indent;
# below this the indent is dropped and the line wraps back at the margin.
WRAP_MIN = 12

# What `---` is drawn as, repeated across the window.
RULE = "─"

# What `> ` is drawn as: the same two columns, so no column moves.
QUOTE_GLYPH = "▎ "

# What the styled spans are tagged with; the theme below maps them to styles
EMPH = "note-emph"
MARKER = "note-marker"
BULLET_SPANS = tuple(f"note-bullet-{depth}" for depth in range(len(BULLET_GLYPHS)))
RULE_SPAN = "note-rule"
# One per heading level; every level past the last wears the last
HEADER_SPANS = tuple(f"note-header-{level}" for level in (1, 2, 3))
LINK = "note-link"
QUOTE = "note-quote"
QUOTE_BAR = "note-quote-bar"
QUOTE_ITEM = "note-quote-item"

# A mark only opens a line when it has nothing but indent before it and a space
# after it - otherwise `-` is a hyphen, `*` is emphasis. A number keeps its own
# figures, and is otherwise a bullet - colored, carried on, nested and unwound
# the same way - whose count `recount` keeps straight.
ITEM_RE = re.compile(r"^(?P<indent>[ \t]*)(?P<marker>[-*] |(?P<number>\d+)\. )")

QUOTE_RE = re.compile(r"^(?P<indent>[ \t]*)(?P<marker>> )")

# A line that's nothing but dashes; three is the shortest run read as
# intentional rather than a stray character.
RULE_RE = re.compile(r"^-{3,}[ \t]*$")


def indent_depth(indent: str) -> int:
    """Nesting depth of leading whitespace (tabs = 1 level, spaces in `INDENT`-wide steps, rounded down)."""

    return len(indent.expandtabs(len(INDENT))) // len(INDENT)


def bullet_glyph(depth: int) -> str:
    """The marker a bullet at `depth` wears, with the space that follows it."""

    return BULLET_GLYPHS[min(depth, len(BULLET_GLYPHS) - 1)] + " "


def ordered_marker(number: int) -> str:
    """The marker a numbered item wears, with the space that follows it."""

    return f"{number}. "


def item_number(marker: str) -> Optional[int]:
    """The number of a numbered item's marker, or None for a bullet (or no marker)."""

    match = ITEM_RE.match(marker)

    return int(match.group("number")) if match and match.group("number") else None


def split_quote(line: str) -> Tuple[str, str]:
    """Split a line into (quote bar, rest); bar is "" when not quoted."""

    match = QUOTE_RE.match(line)

    return (line[: match.end()], line[match.end() :]) if match else ("", line)


def line_prefix(line: str) -> str:
    """A line's opening prefix (quote bar + indent + list marker), or "" - what `enter` carries onto the next line."""

    bar, body = split_quote(line)
    item = ITEM_RE.match(body)

    return bar + (body[: item.end()] if item else "")


def recount(lines: Sequence[str], row: int) -> List[Tuple[int, int, int, str]]:
    """
    Number the list `row` sits in again, top to bottom, so an item opened or
    moved anywhere in it leaves no gap or repeat behind.

    A list is the run of item lines around `row` (a blank line, a plain line or
    a change of quote ends it). Each depth counts on from the item before it at
    that depth; a nested list, or one after a bullet, starts at 1. The list's
    first item keeps the number it was typed with, so `5.` can open one.

    `lines` are as stored. Only markers are rewritten, as (row, start, end,
    marker) edits.
    """

    def item(at: int) -> Optional[Tuple[str, str, str]]:
        bar, body = split_quote(lines[at])
        indent, marker, _ = split_indent(body)

        return (bar, indent, marker) if marker else None

    found = item(row)

    if found is None:
        return []

    bar = found[0]
    first = row

    while first > 0 and (above := item(first - 1)) and above[0] == bar:
        first -= 1

    edits = []
    counts = {}

    for below in range(first, len(lines)):
        found = item(below)

        if found is None or found[0] != bar:
            break

        _, indent, marker = found
        depth = indent_depth(indent)
        number = item_number(marker)

        # Stepping out ends the lists nested deeper
        counts = {level: count for level, count in counts.items() if level <= depth}

        if number is None:
            counts.pop(depth, None)
            continue

        expected = counts.get(depth, number if below == first else 1)
        counts[depth] = expected + 1

        if expected != number:
            start = len(bar) + len(indent)
            edits.append((below, start, start + len(marker), ordered_marker(expected)))

    return edits


def marker_start(line: str) -> int:
    """Column where `line`'s innermost marker starts (list marker first, then quote bar) as a list is exited."""

    bar, body = split_quote(line)
    item = ITEM_RE.match(body)

    if not item:
        return 0

    return len(bar) + len(item.group("indent"))


def split_indent(line: str) -> Tuple[str, str, str]:
    """Split a line (past its quote bar, if any) into (indent, list marker, rest); marker is "" if none."""

    match = ITEM_RE.match(line)

    if match:
        return match.group("indent"), match.group("marker"), line[match.end() :]

    stripped = line.lstrip(" \t")
    return line[: len(line) - len(stripped)], "", stripped


def hanging_prefix(line: str) -> str:
    """
    Prefix (quote bar + indent + list marker) that a wrapped line's
    continuation rows are pushed in under, so they line up with the item's
    words rather than the margin. "" for a line that opens at the margin.
    """

    bar, body = split_quote(line)
    item = ITEM_RE.match(body)

    if item:
        return bar + body[: item.end("marker")]

    # Not a list item, but a hand-indented line (or quote bar) keeps its indent
    indent, _, _ = split_indent(body)

    return bar + indent


def hanging_width(line: str, tab_width: int = len(INDENT)) -> int:
    """Width of `hanging_prefix` in cells, not characters (the quote bar is one character but two columns wide)."""

    return cell_len(hanging_prefix(line).expandtabs(tab_width))


def heading_level(line: str) -> int:
    """How many `#` a heading opens with; 0 if `line` isn't a heading."""

    heading = HEADING_RE.match(line)

    return len(heading.group().rstrip()) if heading else 0


def heading_span(line: str) -> Optional[str]:
    """The span a heading's level wears, or None if `line` isn't a heading."""

    level = heading_level(line)

    return HEADER_SPANS[min(level, len(HEADER_SPANS)) - 1] if level else None


def capitals(text: str) -> str:
    """
    `text` in capitals, one character for one, so the fold's column maps still
    hold: a letter with no single capital (`ß`) stays as it is.
    """

    return "".join(
        char.upper() if len(char.upper()) == 1 else char for char in text
    )


def block_kind(line: str) -> Optional[str]:
    """The span of a line drawn whole across the window (heading, rule), else None."""

    if RULE_RE.match(line):
        return RULE_SPAN

    return heading_span(line)


def draw_line(line: str, raw: bool = False) -> str:
    """
    A stored line as the page shows it: folded, with its quote and bullet marks
    swapped for their glyphs. A glyph takes the column its mark took, so these
    swaps move nothing and the fold's column maps still hold. A top-level
    heading is drawn in capitals. A raw line is handed out as written.
    """

    text = fold_links(line, raw)[0]

    if raw:
        return text

    if heading_level(line) == 1:
        return capitals(text)

    bar, body = split_quote(line)

    if bar:
        start = len(bar) - len(QUOTE_GLYPH)
        text = text[:start] + QUOTE_GLYPH + text[len(bar) :]

    item = ITEM_RE.match(body)

    if item and item.group("number") is None:
        start = len(bar) + item.start("marker")
        glyph = bullet_glyph(indent_depth(item.group("indent")))
        text = text[:start] + glyph + text[start + len(glyph) :]

    return text


def scan_markup(line: str, raw: bool = False) -> Iterator[Tuple[int, int, str]]:
    """
    Styled spans of one stored line, as (start, end, style) offsets in UTF-8
    bytes of the line as drawn - `TextArea.render_line` maps offsets through a
    byte-to-codepoint table, so character offsets would misplace on a multi-byte
    character. A line's opening marks take the same columns stored and drawn.
    """

    drawn = draw_line(line, raw)

    def byte(index: int) -> int:
        return len(drawn[:index].encode("utf-8"))

    block = block_kind(line)

    if block:
        # Whole line, in one style; nothing is parsed inside a title
        yield 0, byte(len(drawn)), block
        return

    bar, body = split_quote(line)

    if bar:
        # A quoted line is still styled for lists/links after this
        yield 0, byte(len(drawn)), QUOTE
        yield 0, byte(len(bar)), QUOTE_BAR

    # Bullet and numbered markers style the same way. Outside a quote, color
    # shows depth; inside one, color shows "quoted" instead (depth is then
    # read from the glyph/indent).
    item = ITEM_RE.match(body)
    if item:
        depth = indent_depth(item.group("indent"))
        span = QUOTE_ITEM if bar else BULLET_SPANS[min(depth, len(BULLET_SPANS) - 1)]

        yield (
            byte(len(bar) + item.start("marker")),
            byte(len(bar) + item.end("marker")),
            span,
        )

    # Underlined exactly where `o` would open it
    for link in fold_links(line, raw)[1]:
        yield byte(link.start), byte(link.end), LINK

    # Off the cursor line the marks are off the page; only the words need styling
    for start, end in folded_emph(line, raw):
        yield byte(start), byte(end), EMPH

    if raw:
        # The stars are real columns here, so they're marked around the words
        for opens, words, closes, end in star_pairs(line):
            yield byte(words), byte(closes), EMPH
            yield byte(opens), byte(words), MARKER
            yield byte(closes), byte(end), MARKER


def scan_note(lines, raw_rows: Container[int] = ()) -> Iterator[list]:
    """
    Styled spans for every stored line of a note, one list per line, landing on
    the text as drawn: raw on `raw_rows`, rendered everywhere else.
    """

    for row, line in enumerate(lines):
        yield list(scan_markup(line, row in raw_rows))
