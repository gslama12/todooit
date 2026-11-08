"""
What a text object stands for, worked out from the text alone. Nothing here
changes anything.

A span runs from a place up to, not including, another. A linewise one is the
whole lines from its start's row to its end's.
"""

from bisect import bisect_right
from dataclasses import dataclass
from typing import Callable, List, Optional, Tuple

from . import motions
from .buffer import Buffer
from .keymap import VimTextObject as Obj
from .motions import Place

# Which run a character belongs to: runs of the same kind make up a word
Kind = Callable[[str], int]


@dataclass(frozen=True)
class Span:
    start: Place
    end: Place
    linewise: bool = False

    @property
    def empty(self) -> bool:
        return not self.linewise and self.start == self.end


def _big_kind(char: str) -> int:
    """For a WORD, all that tells characters apart is whether they're blank."""

    return motions.BLANK if char.isspace() else motions.WORD


# What tells each one's words apart, and whether it's the inside only, as below
WORDS = {
    Obj.INNER_WORD: (motions.char_kind, True),
    Obj.AROUND_WORD: (motions.char_kind, False),
    Obj.INNER_BIG_WORD: (_big_kind, True),
    Obj.AROUND_BIG_WORD: (_big_kind, False),
}

# Each pair's opening and closing character, and whether it's the inside only
PAIRS = {
    Obj.INNER_PARENS: ("()", True),
    Obj.AROUND_PARENS: ("()", False),
    Obj.INNER_BRACKETS: ("[]", True),
    Obj.AROUND_BRACKETS: ("[]", False),
    Obj.INNER_BRACES: ("{}", True),
    Obj.AROUND_BRACES: ("{}", False),
    Obj.INNER_ANGLES: ("<>", True),
    Obj.AROUND_ANGLES: ("<>", False),
}

QUOTES = {
    Obj.INNER_DOUBLE_QUOTES: ('"', True),
    Obj.AROUND_DOUBLE_QUOTES: ('"', False),
    Obj.INNER_SINGLE_QUOTES: ("'", True),
    Obj.AROUND_SINGLE_QUOTES: ("'", False),
    Obj.INNER_BACKTICKS: ("`", True),
    Obj.AROUND_BACKTICKS: ("`", False),
}


def span(
    buffer: Buffer, text_object: Obj, row: int, column: int, count: int
) -> Optional[Span]:
    """What `count` of `text_object` take from this place, or None if nothing."""

    if text_object in (Obj.INNER_PARAGRAPH, Obj.AROUND_PARAGRAPH):
        lines = (
            motions.around_paragraph_lines
            if text_object is Obj.AROUND_PARAGRAPH
            else motions.paragraph_lines
        )
        top, bottom = lines(buffer, row, count)
        return Span((top, 0), (bottom, 0), linewise=True)

    if text_object in PAIRS:
        pair, inner = PAIRS[text_object]
        return _bracket_pair(buffer, row, column, count, pair[0], pair[1], inner)

    if text_object in QUOTES:
        quote, inner = QUOTES[text_object]
        found = _quote_pair(buffer.line(row), column, quote, inner)
    else:
        kind, inner = WORDS[text_object]
        found = _words(buffer.line(row), column, count, kind, inner)

    return Span((row, found[0]), (row, found[1])) if found else None


def _words(
    text: str, column: int, count: int, kind: Kind, inner: bool
) -> Optional[Tuple[int, int]]:
    """
    `iw` takes `count` runs, blanks being one of their own. `aw` takes `count`
    words and the blanks after them, as `_with_blanks` does; from blanks, it
    takes them and the word after, `count` times.
    """

    if not text:
        return None

    column = min(column, len(text) - 1)

    def run_end(at: int) -> int:
        start_kind = kind(text[at])

        while at < len(text) and kind(text[at]) == start_kind:
            at += 1

        return at

    def blank(at: int) -> bool:
        return at < len(text) and kind(text[at]) == motions.BLANK

    start = column

    while start > 0 and kind(text[start - 1]) == kind(text[column]):
        start -= 1

    end = start

    if inner:
        for _ in range(count):
            end = run_end(end) if end < len(text) else end

        return start, end

    from_blanks = blank(start)

    for _ in range(count):
        if blank(end):
            end = run_end(end)

        if end < len(text):
            end = run_end(end)

    return (start, end) if from_blanks else _with_blanks(text, start, end)


def _with_blanks(text: str, start: int, end: int) -> Tuple[int, int]:
    """
    What an `a` object takes: the blanks after it, or with none, the blanks
    before it, unless those are the line's indent.
    """

    if end < len(text) and text[end].isspace():
        while end < len(text) and text[end].isspace():
            end += 1
    elif text[:start].strip():
        while start > 0 and text[start - 1].isspace():
            start -= 1

    return start, end


def _quote_pair(
    text: str, column: int, quote: str, inner: bool
) -> Optional[Tuple[int, int]]:
    """
    As in vim, on one line only: standing on a quote, the pair it's in, pairing
    from the line's start; else the quotes either side, or else the next pair
    along. A quote after a backslash is text.
    """

    quotes = [
        at
        for at, char in enumerate(text)
        if char == quote and (at == 0 or text[at - 1] != "\\")
    ]
    before = [at for at in quotes if at < column]
    after = [at for at in quotes if at > column]

    if column in quotes:
        index = quotes.index(column)
        pair = quotes[index - index % 2 : index - index % 2 + 2]
    elif before and after:
        pair = [before[-1], after[0]]
    else:
        pair = after[:2]

    if len(pair) < 2:
        return None

    if inner:
        return pair[0] + 1, pair[1]

    return _with_blanks(text, pair[0], pair[1] + 1)


class _FlatText:
    """The whole text as one string, to look across lines in."""

    def __init__(self, buffer: Buffer) -> None:
        lines = [buffer.line(row) for row in range(buffer.line_count)]
        self.text = "\n".join(lines)
        self.starts: List[int] = []

        offset = 0
        for line in lines:
            self.starts.append(offset)
            offset += len(line) + 1

    def offset(self, row: int, column: int) -> int:
        return self.starts[row] + column

    def place(self, offset: int) -> Place:
        row = bisect_right(self.starts, offset) - 1
        return row, offset - self.starts[row]


def _bracket_pair(
    buffer: Buffer,
    row: int,
    column: int,
    count: int,
    opening: str,
    closing: str,
    inner: bool,
) -> Optional[Span]:
    """
    The `count`th pair out around the cursor, or else the next pair in the note.
    Its inside leaves out a line break straight after the opening and the
    indent before a closing on a line of its own, and if that leaves whole
    lines, it's those lines.
    """

    note = _FlatText(buffer)
    text = note.text
    at = note.offset(row, min(column, max(0, len(buffer.line(row)) - 1)))

    def match(start: int, step: int, wanted: str, other: str) -> Optional[int]:
        """The `wanted` that isn't taken up by an `other` on the way from `start`."""

        depth = 0
        while 0 <= start < len(text):
            if text[start] == wanted:
                if not depth:
                    return start
                depth -= 1
            elif text[start] == other:
                depth += 1
            start += step
        return None

    on_opening = text[at : at + 1] == opening
    open_at = at if on_opening else match(at - 1, -1, opening, closing)

    for _ in range(count - 1):
        if open_at is None:
            break
        open_at = match(open_at - 1, -1, opening, closing)

    close_at = None if open_at is None else match(open_at + 1, 1, closing, opening)

    # Not inside a pair: the next one along that closes
    if close_at is None and count == 1:
        openings = (o for o in range(at + 1, len(text)) if text[o] == opening)

        for open_at in openings:
            if (close_at := match(open_at + 1, 1, closing, opening)) is not None:
                break

    if open_at is None or close_at is None:
        return None

    if not inner:
        return Span(note.place(open_at), note.place(close_at + 1))

    start, end = open_at + 1, close_at
    line_start = text.rfind("\n", 0, end) + 1
    after_opening = text[start : start + 1] == "\n"
    before_closing = line_start > start and not text[line_start:end].strip()

    if after_opening:
        start += 1

    if before_closing:
        end = line_start - 1

    if start > end:
        return Span(note.place(open_at + 1), note.place(open_at + 1))

    if after_opening and before_closing:
        return Span(note.place(start), note.place(end), linewise=True)

    return Span(note.place(start), note.place(end))
