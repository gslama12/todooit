"""
Markdown in and out of the note: what a copy hands out, what a paste takes in

The note stores its markup already drawn (bullet glyphs, a quote bar, a title
over a rule, zero-width emphasis marks), which no other editor reads. These
two functions translate at the clipboard, so a note copies out as markdown
and markdown pastes in as the markup typing it would have produced. Links
need neither: the note already stores them as markdown.
"""

import re
from typing import List, Optional

from todooit.utils import find_links
from todooit.utils.links import EMPH_MARK

from .markup import (
    INDENT,
    ITEM_RE,
    QUOTE_GLYPH,
    RULE_RE,
    bullet_glyph,
    split_quote,
)

# How the first pasted line meets the line the cursor is on
PASTE_BLOCK = "block"  # cursor opens the line: its markup is converted
PASTE_STRIP = "strip"  # cursor right after a marker: the pasted one is dropped
PASTE_INLINE = "inline"  # cursor mid-line: only emphasis is converted

# What a copy writes for each piece of the note's markup
MD_BULLET = "- "
MD_QUOTE = "> "
MD_HEADER = "# "
MD_RULE = "---"
MD_EMPH = "**"

STORED_EMPH_RE = re.compile(rf"{EMPH_MARK}([^{EMPH_MARK}]+){EMPH_MARK}")

# Markdown's block markup, as it may open a pasted line
FENCE_RE = re.compile(r"^[ \t]*(```|~~~)")
MD_QUOTE_RE = re.compile(r"^(?:[ \t]*>[ \t]?)+")
ATX_RE = re.compile(r"^ {0,3}#{1,6}(?:[ \t]+|$)(?P<title>.*?)(?:[ \t]+#+)?[ \t]*$")
SETEXT_RE = re.compile(r"^ {0,3}(?:=+|-{2,})[ \t]*$")
BREAK_RE = re.compile(r"^ {0,3}([-*_])[ \t]*(?:\1[ \t]*){2,}$")
MD_BULLET_RE = re.compile(r"^(?P<indent>[ \t]*)[-*+](?:[ \t]+|$)")
MD_ORDERED_RE = re.compile(r"^(?P<indent>[ \t]*)(?P<number>\d{1,9})[.)](?:[ \t]+|$)")

# Inline markup. Stars may sit inside a word; underscores may not, so a
# `snake_case_name` stays as written (markdown's own rule).
STAR_EMPH_RE = re.compile(r"(\*{1,3})(?![\s*])(.+?)(?<![\s*])\1(?!\*)")
UNDER_EMPH_RE = re.compile(r"(?<!\w)(_{1,3})(?![\s_])(.+?)(?<![\s_])\1(?!\w)")
CODE_SPAN_RE = re.compile(r"`[^`]*`")
ESCAPE_RE = re.compile(r"\\([\\`*_{}\[\]()#+\-.!>])")

# Escaped characters are parked on private-use code points while emphasis is
# read, so `\*` can't open or close a pair, then put back as plain characters
PARKED = 0xE000


def _emph_out(line: str) -> str:
    """A stored line with its emphasis pairs written as markdown, orphan marks dropped."""

    def write(match: re.Match) -> str:
        phrase = match.group(1)
        words = phrase.strip()

        if not words:
            return phrase

        # Markdown won't open a pair against a space, so spaces go outside it
        lead = phrase[: len(phrase) - len(phrase.lstrip())]
        trail = phrase[len(phrase.rstrip()) :]

        return lead + MD_EMPH + words + MD_EMPH + trail

    return STORED_EMPH_RE.sub(write, line).replace(EMPH_MARK, "")


def to_markdown(text: str) -> str:
    """
    The note's stored text (or a stored excerpt of it) written as markdown.

    A title over its rule becomes a `#` heading, a rule alone `---`, bullets
    `- ` and the quote bar `> `. Nested items are indented to their parent's
    words, which is where markdown looks for them (three columns under `1. `).
    """

    lines = text.split("\n")
    out: List[str] = []

    # Marker width at each depth of the list being written, for the indent
    # its nested items need
    widths = {}
    quoted = False
    row = 0

    while row < len(lines):
        line = lines[row]
        following = lines[row + 1] if row + 1 < len(lines) else ""

        if RULE_RE.match(line):
            out.append(MD_RULE)
            widths, quoted = {}, False
            row += 1
            continue

        if line.strip() and RULE_RE.match(following):
            out.append(MD_HEADER + _emph_out(line.strip()))
            widths, quoted = {}, False
            row += 2
            continue

        bar, body = split_quote(line)

        # A line straight after a quote would be read as more of it
        if quoted and not bar and line.strip():
            out.append("")

        quoted = bool(bar)

        if bar:
            bar = bar.replace(QUOTE_GLYPH, MD_QUOTE)

        item = ITEM_RE.match(body)

        if item:
            depth = len(item.group("indent").expandtabs(len(INDENT))) // len(INDENT)
            marker = MD_BULLET if item.group("number") is None else item.group("marker")

            widths = {level: width for level, width in widths.items() if level < depth}
            indent = "".join(" " * widths.get(level, len(INDENT)) for level in range(depth))
            widths[depth] = len(marker)

            body = indent + marker + body[item.end() :]
        else:
            widths = {}

        out.append(bar + _emph_out(body))
        row += 1

    return "\n".join(out)


def _emph_in(text: str) -> str:
    """Markdown emphasis in a run of plain text (no code, no links) as the note's marks."""

    parked = {}

    def park(match: re.Match) -> str:
        code = chr(PARKED + len(parked))
        parked[code] = match.group(1)
        return code

    text = ESCAPE_RE.sub(park, text)

    def mark(match: re.Match) -> str:
        return EMPH_MARK + match.group(2) + EMPH_MARK

    text = STAR_EMPH_RE.sub(mark, text)
    text = UNDER_EMPH_RE.sub(mark, text)

    for code, character in parked.items():
        text = text.replace(code, character)

    return text


def inline_markdown(text: str) -> str:
    """One line's inline markdown converted, code spans and links left exactly as written."""

    kept = [(match.start(), match.end()) for match in CODE_SPAN_RE.finditer(text)]
    kept += [
        (link.start, link.end)
        for link in find_links(text)
        if not any(start <= link.start < end for start, end in kept)
    ]

    out = []
    at = 0

    for start, end in sorted(kept):
        if start < at:
            continue

        out.append(_emph_in(text[at:start]))
        out.append(text[start:end])
        at = end

    out.append(_emph_in(text[at:]))

    return "".join(out)


def _indent_of(line: str) -> Optional[str]:
    """The indent of a markdown list item, or None if `line` isn't one."""

    match = MD_BULLET_RE.match(line) or MD_ORDERED_RE.match(line)

    return match.group("indent") if match else None


def _levels(lines: List[str]):
    """
    A function giving a markdown list item's nesting level from its indent.

    Files nest by 2, 3 or 4 spaces (or tabs), so one level is read off the
    paste: the smallest step in from its shallowest item. A tab is a level.
    """

    spaces = []

    for line in lines:
        indent = _indent_of(line)

        if indent is not None and "\t" not in indent:
            spaces.append(len(indent))

    base = min(spaces, default=0)
    steps = [count - base for count in spaces if count > base]
    unit = min(steps, default=len(INDENT))

    def level(indent: str) -> int:
        tabs = indent.count("\t")
        count = len(indent.replace("\t", ""))

        return tabs + max(0, count - base) // unit

    return level


def from_markdown(
    text: str,
    rule: str,
    first: str = PASTE_BLOCK,
    above: str = "",
) -> str:
    """
    Pasted markdown as the note stores it.

    Headings of any depth (`#`..`######`, or underlined with `===`/`---`)
    become a title over `rule`; a thematic break becomes `rule` alone; `-`,
    `*` and `+` bullets the glyph for their depth; `1.` and `1)` items
    `1. `; `>` (nested or not) the quote bar; `*`, `**`, `_`, `__` emphasis
    the note's one emphasis. Code blocks, code spans and links pass through.

    `first` says how much of the first line's markup applies (see the PASTE_
    constants); `above` is the note's line above it, so a rule pasted under
    text keeps a blank line between and isn't read as that text's underline.
    """

    lines = text.replace("\r\n", "\n").replace("\r", "\n").split("\n")

    # Hard breaks (trailing spaces) mean nothing here; the last line is left
    # alone, since it runs on into the line the cursor was on
    lines = [line.rstrip() for line in lines[:-1]] + lines[-1:]

    fenced = []
    inside = False

    for line in lines:
        opens = bool(FENCE_RE.match(line))
        fenced.append(inside or opens)

        if opens:
            inside = not inside

    level = _levels(
        [
            MD_QUOTE_RE.sub("", line)
            for row, line in enumerate(lines)
            if not fenced[row] and (row or first == PASTE_BLOCK)
        ]
    )

    out: List[str] = []

    def previous() -> str:
        return out[-1] if out else above

    row = 0

    while row < len(lines):
        line = lines[row]
        following = lines[row + 1] if row + 1 < len(lines) else None

        if fenced[row]:
            out.append(line)
            row += 1
            continue

        if row == 0 and first != PASTE_BLOCK:
            if first == PASTE_STRIP:
                line = _strip_block(line)

            out.append(inline_markdown(line))
            row += 1
            continue

        quote = MD_QUOTE_RE.match(line)
        bar = QUOTE_GLYPH if quote else ""
        body = line[quote.end() :] if quote else line

        heading = ATX_RE.match(body)

        if heading:
            title = inline_markdown(heading.group("title"))

            # Headings are a whole-line construct; inside a quote only the words stay
            out.append(bar + title if bar else title + "\n" + rule)
            row += 1
            continue

        if BREAK_RE.match(body) and not bar:
            if previous().strip() and not RULE_RE.match(previous()):
                out.append("")

            out.append(rule)
            row += 1
            continue

        bullet = MD_BULLET_RE.match(body)
        ordered = MD_ORDERED_RE.match(body)

        if bullet or ordered:
            match = bullet or ordered
            depth = level(match.group("indent"))
            marker = (
                bullet_glyph(depth) if bullet else f"{int(match.group('number'))}. "
            )

            out.append(bar + INDENT * depth + marker + inline_markdown(body[match.end() :]))
            row += 1
            continue

        # Text underlined with `===`/`---` is a heading too
        if (
            not bar
            and body.strip()
            and following is not None
            and not fenced[row + 1]
            and SETEXT_RE.match(following)
        ):
            out.append(inline_markdown(body.strip()) + "\n" + rule)
            row += 2
            continue

        out.append(bar + inline_markdown(body))
        row += 1

    return "\n".join(out)


def _strip_block(line: str) -> str:
    """A markdown line without the block marker (quote, heading, list) it opens with."""

    quote = MD_QUOTE_RE.match(line)
    body = line[quote.end() :] if quote else line

    heading = ATX_RE.match(body)

    if heading:
        return heading.group("title")

    match = MD_BULLET_RE.match(body) or MD_ORDERED_RE.match(body)

    return body[match.end() :] if match else body
