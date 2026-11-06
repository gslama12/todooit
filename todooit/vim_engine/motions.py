"""
Where a motion lands, worked out from the text alone. Nothing here moves anything.

A word is a run of letters, digits and `_` (umlauts are letters), or a run of
anything else that isn't blank, as in vim.
"""

import unicodedata
from typing import Callable, Iterable, Tuple

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


def first_non_blank(text: str) -> int:
    """A line of nothing but blanks has none: its last character, then."""

    stripped = len(text) - len(text.lstrip())

    return min(stripped, max(0, len(text) - 1))


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
