"""
The note's markdown-ish markup: constants, regexes and pure line parsing
"""

import re
from typing import Container, Iterator, List, Optional, Sequence, Tuple

from rich.cells import cell_len

from todooit.utils import (
    find_links,
    fold_links,
)
from todooit.utils.links import (
    EMPH_MARK,
    folded_emph,
    mark_pairs,
)

# Stored as the actual glyph (not a "- " swapped at render time) since a
# TextArea draws exactly the text it holds. One glyph per nesting level; past
# the last, the deepest glyph is reused.
BULLET_GLYPHS = ("•", "◦", "▪")

# One nesting level, in columns.
INDENT = "  "

# Minimum columns a wrapped continuation line must keep after its indent;
# below this the indent is dropped and the line wraps back at the margin.
WRAP_MIN = 12

# A header is a title line followed by a rule line. The same rule with no
# title above it is a plain separator - told apart by whether there are words
# directly above it.
RULE = "─"

# Rule width, before a narrow window shortens it.
HEADER_WIDTH = 60

# Quote bar glyph, stored in place of markdown's `>` (converted on input, so
# what's on disk is already what's drawn).
QUOTE_GLYPH = "▎ "
QUOTE_MARK = ">"

# A mark only opens a line when it has nothing but indent before it and a
# space after it - otherwise `-` is a hyphen, `*` is emphasis, `#` a number
# sign.

# Typed forms of a bullet; both map to the same glyph (looked up by depth,
# not stored here).
BULLET_MARKS = ("-", "*")

# `*` also opens emphasis when a pair surrounds a phrase; followed by a space
# it's a bullet instead.
EMPH_STAR = "*"

# Markdown heading marker; any depth of `#` collapses to this note's one
# heading style.
HEADER_MARK = "#"

# `---` becomes the rule (a `-` alone is a bullet instead).
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

# Emphasis is delimited by EMPH_MARK, a zero-width space (defined in
# utils/links.py, where the folding lives) so it costs no columns and holds
# no cursor position - unlike `*`, which occupies a column.
#
# `*` pairs are still recognized (pasted or legacy notes) using markdown's own
# rule: something between the stars, neither side touching a space, so
# `a * b * c` stays arithmetic.
EMPH_RE = re.compile(
    rf"{EMPH_MARK}(?P<emph>[^{EMPH_MARK}]+){EMPH_MARK}"
    r"|\*(?P<star>[^*\s](?:[^*]*[^*\s])?)\*"
)

# A list item: a bullet glyph, or a number. A number keeps no glyph, and is
# otherwise a bullet - colored, carried on, nested and unwound the same way -
# whose count `recount` keeps straight.
ITEM_RE = re.compile(
    rf"^(?P<indent>[ \t]*)(?P<marker>[{''.join(BULLET_GLYPHS)}] |(?P<number>\d+)\. )"
)

QUOTE_RE = re.compile(rf"^(?P<indent>[ \t]*)(?P<marker>{QUOTE_GLYPH})")

# A line that's nothing but rule; three is the shortest run read as
# intentional rather than a stray character.
RULE_RE = re.compile(rf"^{RULE}{{3,}}[ \t]*$")


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

    Only markers are rewritten (lines may carry folded links, which a whole-line
    rewrite would lose), as (row, start, end, marker) edits.
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


def star_pair(line: str, column: int) -> Optional[int]:
    """Column of the `*` pairing with the one at `column`, or None if it closes nothing."""

    opening = line.rfind(EMPH_STAR, 0, column)

    if opening < 0:
        return None

    inner = line[opening + 1 : column]

    if not inner or inner[0].isspace() or inner[-1].isspace():
        return None

    return opening


def star_closing(line: str, column: int) -> Optional[int]:
    """Column of the `*` pairing with one typed at `column` to open it, or None if it opens nothing."""

    # star_pair run backwards: on the reversed line the closing star is an opening one.
    opening = star_pair(line[::-1], len(line) - column)
    return None if opening is None else len(line) - 1 - opening


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


def tidy_marks(text: str) -> str:
    """
    Strip emphasis marks that lost their pair (e.g. an edit cut a pair in
    two). Run on save, not every keystroke - the fold hides orphans anyway.
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
    Styled spans of one line, as (start, end, style) offsets in UTF-8 bytes -
    `TextArea.render_line` maps offsets through a byte-to-codepoint table, so
    character offsets would misplace on a multi-byte character.

    `following` is the next line, needed to recognize a header (title + rule
    below). `line` is the line as *drawn* (links folded, emphasis marks
    removed); `links`/`emph` are recomputed from `line` if not given.
    """

    def byte(index: int) -> int:
        return len(line[:index].encode("utf-8"))

    links = links if links is not None else find_links(line)
    emph = emph if emph is not None else folded_emph(line)

    if RULE_RE.match(line):
        yield 0, byte(len(line)), RULE_SPAN
        return

    if RULE_RE.match(following) and line.strip():
        # Whole line is the header; no bullets/emphasis parsed inside a title
        yield 0, byte(len(line)), HEADER
        return

    bar, body = split_quote(line)

    if bar:
        # A quoted line is still styled for lists/links after this
        yield 0, byte(len(line)), QUOTE
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
    for link in links:
        yield byte(link.start), byte(link.end), LINK

    # Zero-width marks are already off the page; only the words need styling
    for start, end in emph:
        yield byte(start), byte(end), EMPH

    # Star-delimited emphasis (pasted/mid-typing): stars are real columns, so
    # the words are styled first and the stars marked over them
    for match in EMPH_RE.finditer(line):
        if match.group("star") is None:
            continue

        start, end = match.span()

        yield byte(start + 1), byte(end - 1), EMPH
        yield byte(start), byte(start + 1), MARKER
        yield byte(end - 1), byte(end), MARKER


def scan_note(lines, raw_rows: Container[int] = ()) -> Iterator[list]:
    """
    Styled spans for every line of a note, one list per line.

    Walks the whole note (not line by line) because a header needs the line
    below it. `lines` are as *stored*; spans land on the *drawn* text (links
    folded to their names, except on `raw_rows`), folded here so spans and text
    always match.
    """

    drawn = []
    found = []
    lit = []

    for row, line in enumerate(lines):
        raw = row in raw_rows
        text, links = fold_links(line, raw)

        drawn.append(text)
        found.append(links)
        lit.append(folded_emph(line, raw))

    for row, line in enumerate(drawn):
        following = drawn[row + 1] if row + 1 < len(drawn) else ""

        yield list(scan_markup(line, following, found[row], lit[row]))
