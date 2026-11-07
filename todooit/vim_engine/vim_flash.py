"""
`vim_flash`: jump to any text on screen by typing some of it, then a label.

Follows flash.nvim's defaults, read from its source (labeler.lua, state.lua):

- All the letters of the alphabet, then all of them in capitals. A label that
  could carry on the typed text is dropped in both its cases, wherever it would.
- Labels go out nearest first, by distance along the text. When they run out,
  the matches left over go without; there are no further pages of them.
- A match keeps a lowercase label it was given while the text narrows.
- `enter` goes to the next match after the cursor, round the end of the note. If
  that's off screen, it's the previous one instead, if that isn't.

Shares nothing with the task pane's flash mode.
"""

import re
from dataclasses import dataclass
from typing import Dict, Iterator, List, Optional, Tuple

from .buffer import Buffer

Place = Tuple[int, int]

# Nearest targets get the easiest keys: the home row first (qwertz), then the
# rest of the letters. The default for `api.vars.vim_flash_alphabet`.
VIM_FLASH_ALPHABET = "asdfghjklöqwertzuiopyxcvbnm"


@dataclass(frozen=True)
class VimFlashMatch:
    """Some text on screen that was typed. All columns are raw ones."""

    row: int
    start: int
    end: int
    label: Optional[str]

    # The column on the row as drawn that the label goes over, just past the match
    label_column: int


@dataclass(frozen=True)
class VimFlashView:
    """What a host can show of a `vim_flash`."""

    text: str = ""

    # Top to bottom
    matches: Tuple[VimFlashMatch, ...] = ()

    # Where `enter` goes, if anywhere
    first: Optional[Place] = None


class VimFlashMode:
    """One `vim_flash` from opening to closing, as the text typed so far decides."""

    def __init__(self, buffer: Buffer, alphabet: str) -> None:
        self._buffer = buffer
        self.origin: Place = buffer.cursor

        # An uppercase of one letter can be two, which simply come out as letters
        self._labels = list(dict.fromkeys(alphabet + alphabet.upper()))

        # The lowercase labels given so far, for a match to keep
        self._given: Dict[Place, str] = {}

        self.text = ""
        self.view = VimFlashView()

    def narrow(self, text: str) -> None:
        """Look for `text` instead, on the rows on screen as they're drawn now."""

        self.text = text

        rows = self._buffer.visible_rows
        spans = list(self._found(rows))
        free = self._free_labels(spans)

        # What's made up for a shortened address has one place behind all of it
        targets = {
            self._place(row, start): (row, end) for row, start, end in reversed(spans)
        }
        places = sorted(targets)
        labels = self._label(places, free, rows)

        self.view = VimFlashView(
            text,
            tuple(
                VimFlashMatch(
                    row, place[1], self._end(row, end), labels.get(place), end
                )
                for place, (row, end) in sorted(targets.items())
            ),
            self._first(rows),
        )

    def labelled(self, key: str) -> Optional[Place]:
        """Where the label `key` goes, if it's one on show."""

        for match in self.view.matches:
            if match.label == key:
                return match.row, match.start

        return None

    def _found(self, rows: range) -> Iterator[Tuple[int, int, int]]:
        """Each match in these rows, in drawn columns. As in flash.nvim, they overlap."""

        if not self.text:
            return

        # Smartcase: the case counts only if there's a capital in what was typed
        flags = 0 if any(char.isupper() for char in self.text) else re.IGNORECASE
        pattern = re.compile(f"(?=({re.escape(self.text)}))", flags)

        for row in rows:
            for found in pattern.finditer(self._buffer.drawn_line(row)):
                yield row, found.start(1), found.end(1)

    def _place(self, row: int, column: int) -> Place:
        return row, self._buffer.stored_column(row, column)

    def _end(self, row: int, column: int) -> int:
        """Just past the last character, hidden markup after it staying out of it."""

        return self._buffer.stored_column(row, column - 1) + 1

    def _free_labels(self, spans: List[Tuple[int, int, int]]) -> List[str]:
        """The labels that nothing here could be carried on with."""

        drawn_line = self._buffer.drawn_line
        following = {drawn_line(row)[end:end + 1].lower() for row, _, end in spans}

        return [label for label in self._labels if label.lower() not in following]

    def _label(
        self, places: List[Place], free: List[str], rows: range
    ) -> Dict[Place, str]:
        """Who gets which label: those a match already had, then nearest first."""

        labels: Dict[Place, str] = {}

        for place in places:
            kept = self._given.get(place)

            if kept in free:
                labels[place] = kept
                free.remove(kept)

        # Along the text as if it were one long line, so rows outweigh columns.
        # Python's sort is stable, so a tie goes to whichever is higher up.
        width = 1 + max((len(self._buffer.line(row)) for row in rows), default=0)
        row, column = self.origin
        origin = row * width + column

        for place in sorted(
            places, key=lambda place: abs(place[0] * width + place[1] - origin)
        ):
            if not free:
                break

            if place not in labels:
                labels[place] = label = free.pop(0)

                if label == label.lower():
                    self._given[place] = label

        return labels

    def _first(self, rows: range) -> Optional[Place]:
        """Where `enter` goes: the whole note counts, but it has to land on screen."""

        note = range(self._buffer.line_count)
        places = [self._place(row, start) for row, start, _ in self._found(note)]

        if not places:
            return None

        origin = self.origin
        ahead = next((place for place in places if place > origin), places[0])

        if ahead[0] in rows:
            return ahead

        behind = next(
            (place for place in reversed(places) if place < origin), places[-1]
        )

        return behind if behind[0] in rows else None
