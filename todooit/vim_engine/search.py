"""
What a search looks for, and where it is in the text. Plain text, never patterns.
"""

import re
from dataclasses import dataclass
from typing import Iterator, NamedTuple, Optional, Tuple

from . import motions
from .buffer import Buffer

# Where a match is: (row, start column, end column)
MatchSpan = Tuple[int, int, int]


class SearchHit(NamedTuple):
    """Where a search got to, and whether it wrapped around the note's end for it."""

    place: motions.Place
    wrapped: bool


@dataclass(frozen=True)
class Search:
    """One thing to look for. Case counts only if it has a capital in it."""

    text: str

    # A whole word, as `*` asks for, whose case never counts
    whole_word: bool = False

    def matches(self, buffer: Buffer) -> Iterator[MatchSpan]:
        """Every match top to bottom in the raw text. As in vim, none overlap."""

        ignores_case = self.whole_word or not any(c.isupper() for c in self.text)
        pattern = re.compile(re.escape(self.text), re.I if ignores_case else 0)

        for row in range(buffer.line_count):
            line = buffer.line(row)

            for found in pattern.finditer(line):
                if not self.whole_word or motions.is_whole_word(line, *found.span()):
                    yield row, found.start(), found.end()

    def next_from(
        self, buffer: Buffer, place: motions.Place, *, forward: bool
    ) -> Optional[SearchHit]:
        """The nearest match beyond `place` going this way, if there are any at all."""

        places = [(row, start) for row, start, _ in self.matches(buffer)]

        if not places:
            return None

        if forward:
            ahead = [found for found in places if found > place]
            return SearchHit(ahead[0], False) if ahead else SearchHit(places[0], True)

        behind = [found for found in places if found < place]
        return SearchHit(behind[-1], False) if behind else SearchHit(places[-1], True)


@dataclass
class SearchMemory:
    """The last search, kept by whoever outlives a single engine."""

    last: Optional[Search] = None
