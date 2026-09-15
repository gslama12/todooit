"""
Completing the `#project` in a typed line, the way a shell completes a path

A project lives in a tree and is written like a path -- `work/api` -- so the
name of one is finished the way a filename is finished at a prompt: as much of
it as every match agrees on, and then, once they stop agreeing, one match at a
time. A project with children is left open with the separator after it, the
way completing a directory leaves the slash, because there is probably another
step still to type; one with none is finished off with a space, because there
is not.

Only the working out is here. Which projects there are is the app's business,
and arrives as a list of `Candidate`; where the completed text goes is the
overlay's, and it takes back a string.
"""

import re
from dataclasses import dataclass
from typing import List, Optional, Sequence, Tuple

from .quick_add import PATH_SEPARATOR, PROJECT_MARKER

# The `#project` under the cursor, at whatever stage of being typed it is in.
# Looser than the parser's own marker pattern, which only matches a field that
# is finished: half a name is the thing there is to complete, a bare `#` is
# the whole list, and a quote nobody has closed yet is still an opening quote.
TOKEN = re.compile(rf'(?:(?<=\s)|\A){re.escape(PROJECT_MARKER)}("[^"]*"?|\S*)')


@dataclass(frozen=True)
class Candidate:
    """
    One project the line could be completed to, as a path from the root down
    """

    steps: Tuple[str, ...]

    # Whether there is anything inside it, which is what decides how a
    # finished completion is punctuated
    has_children: bool = False

    @property
    def name(self) -> str:
        """The project's own name, which is the step being completed"""

        return self.steps[-1]


@dataclass(frozen=True)
class Token:
    """
    The `#project` the cursor is standing in, and where it sits in the line

    `start` and `end` bracket what was typed after the marker, quotes and
    all, so that replacing that span is all a completion has to do. `text` is
    the same thing with the quotes taken off, which is what it means.
    """

    start: int
    end: int
    text: str

    @property
    def steps(self) -> List[str]:
        """
        What was typed, as the steps of a path -- the last one half finished
        """

        return [step.strip() for step in self.text.split(PATH_SEPARATOR)]

    @property
    def partial(self) -> str:
        """The name being completed, which is the last step and may be empty"""

        return self.steps[-1]

    @property
    def anchor(self) -> Tuple[str, ...]:
        """
        The steps named above it, which say which of two same-named projects
        """

        return tuple(step for step in self.steps[:-1] if step)


def find_token(value: str, cursor: int) -> Optional[Token]:
    """
    The `#project` the cursor is in, or None when it is not in one at all

    The cursor is what makes a token the one being typed: a line can name a
    project and then go on talking about something else, and the completion
    has nothing to say about the field that was finished three words ago.
    """

    for match in TOKEN.finditer(value):
        start, end = match.span(1)

        if start <= cursor <= end:
            return Token(start, end, match.group(1).strip('"'))

    return None


def matching(token: Token, pool: Sequence[Candidate]) -> List[Candidate]:
    """
    Every project the half typed name could still turn into

    A name on its own matches at any depth, which is how a project is spoken
    about and what `find_projects` already does with a finished one. Steps
    named above it match bottom up, so `work/ap` is the `ap...` inside a
    `work` and not every `ap...` there is.

    Shallowest first: a project near the top of the tree is the likelier one
    to have been meant by a couple of letters.
    """

    partial = token.partial.lower()
    anchor = tuple(step.lower() for step in token.anchor)

    found = [
        candidate
        for candidate in pool
        if candidate.name.lower().startswith(partial)
        and _above(candidate, len(anchor)) == anchor
    ]

    return sorted(found, key=lambda c: (len(c.steps), [s.lower() for s in c.steps]))


def common_prefix(names: Sequence[str]) -> str:
    """
    As much of a name as every match agrees on, in the first one's spelling

    Matching ignores case, so the agreed prefix is spelled the way a real
    project spells it rather than the way it was typed: completing `#WO` to
    `work` is the answer, and `#WOrk` would be a third spelling of it.
    """

    if not names:
        return ""

    first = names[0]
    length = len(first)

    for name in names[1:]:
        length = min(length, len(name))

        while length and name[:length].lower() != first[:length].lower():
            length -= 1

    return first[:length]


def minimal_path(candidate: Candidate, pool: Sequence[Candidate]) -> Tuple[str, ...]:
    """
    The shortest tail of a project's path that means only that project

    A name is enough when nothing else is called it, which is the usual case
    and the shortest thing to type. Where two projects share one, as much of
    the way up as it takes to tell them apart is added -- which is the same
    `parent/child` the overlay suggests when a name turns out to be ambiguous.
    """

    for depth in range(1, len(candidate.steps)):
        suffix = candidate.steps[-depth:]

        # Counted rather than compared against the candidate, which need not
        # be the very object the pool holds: the project itself is one of the
        # projects a path pointing at it reaches, and a second one is what
        # makes the path ambiguous
        if sum(_ends_with(other.steps, suffix) for other in pool) <= 1:
            return suffix

    return candidate.steps


def completion(
    token: Token, candidate: Candidate, pool: Sequence[Candidate]
) -> str:
    """
    The path a chosen project goes into the line as

    Never shorter than what was typed: someone who has written `work/` has
    said where they are looking, and having it replaced by a bare name under
    their hands would be answering a different question.
    """

    depth = max(len(token.anchor) + 1, len(minimal_path(candidate, pool)))

    return PATH_SEPARATOR.join(candidate.steps[-depth:])


def extended(token: Token, partial: str) -> str:
    """
    The token's own path with the name it is completing grown a little

    What tab does while the matches still agree: the steps above are left
    exactly as they were typed, since they are not what is being completed.
    """

    return PATH_SEPARATOR.join([*token.anchor, partial])


def written(path: str, trailing: str = "") -> str:
    """
    A completed path as it is written into the line, quoted where it must be

    A name with a space in it only survives being read back inside quotes,
    and the quotes have to hold the whole field: `#"my work"/api` is read as
    the project `my work` followed by a stray `/api`. So the separator goes
    inside them and the space that ends the field stays outside.
    """

    if trailing == PATH_SEPARATOR:
        return _quoted(path + trailing)

    return _quoted(path) + trailing


def _quoted(text: str) -> str:
    return f'"{text}"' if " " in text else text


def _above(candidate: Candidate, depth: int) -> Tuple[str, ...]:
    """
    The `depth` steps sitting directly above a project, lowercased to compare

    Short where the project is not that deep, which is what stops a two step
    path from matching a project living at the top of the tree.
    """

    if not depth:
        return ()

    return tuple(step.lower() for step in candidate.steps[-depth - 1 : -1])


def _ends_with(steps: Sequence[str], suffix: Sequence[str]) -> bool:
    """Whether a path finishes with the steps of another, whatever the case"""

    if len(steps) < len(suffix):
        return False

    return [step.lower() for step in steps[-len(suffix) :]] == [
        step.lower() for step in suffix
    ]
