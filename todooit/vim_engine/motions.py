"""
Where a motion lands, worked out from the text alone. Nothing here moves anything.

A word is a run of letters, digits and `_` (umlauts are letters), or a run of
anything else that isn't blank, as in vim.
"""

import unicodedata
from typing import Callable, Iterable, Optional, Tuple

from .buffer import Buffer

Place = Tuple[int, int]

# One step of a motion that can be repeated: from a place, to the next
Step = Callable[[Buffer, int, int], Place]

_BLANK, _WORD, _PUNCTUATION = range(3)


def _kind(char: str) -> int:
    if char.isspace():
        return _BLANK

    # A combining mark is the rest of a letter: an umlaut can be stored as two
    is_word = char.isalnum() or char == "_" or unicodedata.combining(char)

    return _WORD if is_word else _PUNCTUATION


def is_whole_word(text: str, start: int, end: int) -> bool:
    """Whether what's between these columns has no word running on from either end."""

    return (start == 0 or _kind(text[start - 1]) != _WORD) and (
        end == len(text) or _kind(text[end]) != _WORD
    )


def word_at(text: str, column: int) -> Optional[Tuple[int, int]]:
    """Where the word under `column` is, or else the next one along, as `*` takes."""

    start = column

    while start < len(text) and _kind(text[start]) != _WORD:
        start += 1

    if start == len(text):
        return None

    end = start

    while end < len(text) and _kind(text[end]) == _WORD:
        end += 1

    while start > 0 and _kind(text[start - 1]) == _WORD:
        start -= 1

    return start, end


def next_word_start(buffer: Buffer, row: int, column: int) -> Place:
    """`w`: an empty line counts as a word; the very last character ends the road."""

    text = buffer.line(row)

    if column < len(text) and (kind := _kind(text[column])) != _BLANK:
        while column < len(text) and _kind(text[column]) == kind:
            column += 1

    while True:
        while column < len(text) and _kind(text[column]) == _BLANK:
            column += 1

        if column < len(text):
            return row, column

        if row == buffer.line_count - 1:
            return row, max(0, len(text) - 1)

        row, column = row + 1, 0
        text = buffer.line(row)

        if not text:
            return row, 0


def word_operand_end(buffer: Buffer, row: int, column: int) -> Place:
    """
    Where the last `w` of an operator stops: at the next word on this line, or
    else the line's end, so `dw` on its last word leaves the line break. On an
    empty line there's only the next line's start to go to.
    """

    text = buffer.line(row)

    if not text:
        return (row + 1, 0) if row < buffer.line_count - 1 else (row, 0)

    if column < len(text) and _kind(text[column]) != _BLANK:
        _, column = word_change_end(buffer, row, column)

    while column < len(text) and _kind(text[column]) == _BLANK:
        column += 1

    return row, column


def word_change_end(buffer: Buffer, row: int, column: int) -> Place:
    """Where the last `w` of `c` stops, on a word: the end of it, blanks left out."""

    text = buffer.line(row)

    if column < len(text):
        kind = _kind(text[column])

        while column < len(text) and _kind(text[column]) == kind:
            column += 1

    return row, column


def previous_word_start(buffer: Buffer, row: int, column: int) -> Place:
    """`b`: as `w`, an empty line counts as a word."""

    text = buffer.line(row)
    column -= 1

    while column < 0 or _kind(text[column]) == _BLANK:
        if column >= 0:
            column -= 1
            continue

        if row == 0:
            return 0, 0

        row -= 1
        text = buffer.line(row)

        if not text:
            return row, 0

        column = len(text) - 1

    kind = _kind(text[column])

    while column > 0 and _kind(text[column - 1]) == kind:
        column -= 1

    return row, column


def next_word_end(buffer: Buffer, row: int, column: int) -> Place:
    """`e`: unlike `w` and `b`, this passes over empty lines."""

    text = buffer.line(row)
    column += 1

    while column >= len(text) or _kind(text[column]) == _BLANK:
        if column < len(text):
            column += 1
            continue

        if row == buffer.line_count - 1:
            return row, max(0, len(text) - 1)

        row, column = row + 1, 0
        text = buffer.line(row)

    kind = _kind(text[column])

    while column + 1 < len(text) and _kind(text[column + 1]) == kind:
        column += 1

    return row, column


def next_paragraph(buffer: Buffer, row: int, column: int) -> Place:
    """`}`: the next empty line after some text, or else the note's last character."""

    last = buffer.line_count - 1

    while row < last and not buffer.line(row):
        row += 1

    while row < last:
        row += 1

        if not buffer.line(row):
            return row, 0

    return last, max(0, len(buffer.line(last)) - 1)


def previous_paragraph(buffer: Buffer, row: int, column: int) -> Place:
    """`{`: the last empty line before some text, or else the note's first character."""

    while row > 0 and not buffer.line(row):
        row -= 1

    while row > 0:
        row -= 1

        if not buffer.line(row):
            return row, 0

    return 0, 0


def _blank(buffer: Buffer, row: int) -> bool:
    """Unlike `{` and `}`, a paragraph object takes a line of blanks as blank too."""

    return not buffer.line(row).strip()


def paragraph_lines(buffer: Buffer, row: int, runs: int) -> Tuple[int, int]:
    """
    The rows of `runs` runs of text or blank lines in a row, starting with the one
    around `row`, for as many as there are.
    """

    last = buffer.line_count - 1
    top = bottom = row

    while top > 0 and _blank(buffer, top - 1) == _blank(buffer, row):
        top -= 1

    for run in range(runs):
        if run and bottom < last:
            bottom += 1

        while bottom < last and _blank(buffer, bottom + 1) == _blank(buffer, bottom):
            bottom += 1

    return top, bottom


def around_paragraph_lines(buffer: Buffer, row: int, count: int) -> Tuple[int, int]:
    """
    `count` paragraphs with the blanks after each, or if the note ends first, with
    the blanks before the first instead.
    """

    top, bottom = paragraph_lines(buffer, row, count * 2)

    if not _blank(buffer, top) and not _blank(buffer, bottom):
        while top > 0 and _blank(buffer, top - 1):
            top -= 1

    return top, bottom


def first_non_blank(text: str) -> int:
    """A line of nothing but blanks has none: its last character, then."""

    return min(indent_width(text), max(0, len(text) - 1))


def indent_width(text: str) -> int:
    """How many blanks open the line."""

    return len(text) - len(text.lstrip())


def find_targets(
    buffer: Buffer, rows: Iterable[int], char: str, offset: int
) -> Tuple[Place, ...]:
    """
    Where `f F t T` can land for `char` on these rows, top to bottom: `offset`
    away from each one, if that's still on its line.
    """

    targets = []

    for row in rows:
        text = buffer.line(row)
        targets += [
            (row, column + offset)
            for column, found in enumerate(text)
            if found == char and 0 <= column + offset < len(text)
        ]

    return tuple(targets)
