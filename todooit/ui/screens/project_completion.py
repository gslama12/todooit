"""
Shell-style completion of a half typed project name, with a list of matches

Mixed into quick add (where the name is a `#field` of the line) and move
(where the name is the whole line). The pure matching logic lives in
`todooit.utils.project_complete`; this module knows about the database.
"""

from typing import List, Optional, Sequence, Tuple

from rich.console import RenderableType
from rich.style import Style
from rich.table import Table
from rich.text import Text

from todooit.api import Project
from todooit.utils.project_complete import (
    Candidate,
    Token,
    common_prefix,
    completion,
    extended,
    matching,
    written,
)
from todooit.utils.quick_add import PATH_SEPARATOR, split_path

from .panel import PROJECT_ICON

# How many matches are listed at once; the cursor scrolls over the rest
MAX_SUGGESTIONS = 8

# Under the last row when the list is longer than the window
MORE = "…and {} more"


def find_projects(name: str) -> List[Project]:
    """
    Every project a typed name could mean

    A bare name matches at any depth; a path (`work/api`) is matched from the
    bottom up, which disambiguates same-named projects.
    """

    steps = split_path(name)

    if not steps:
        return []

    def matches(project: Project) -> bool:
        node: Optional[Project] = project

        for step in reversed(steps):
            if node is None or node.is_root:
                return False

            if node.description.strip().lower() != step.lower():
                return False

            node = node.parent_project

        return True

    return [project for project in Project.all() if matches(project)]


def build_project(steps: Sequence[str]) -> Project:
    """Creates the project at a path from the root, plus any missing parents"""

    parent = Project._get_or_create_root()

    for step in steps:
        existing = [
            child
            for child in parent.projects
            if child.description.strip().lower() == step.lower()
        ]

        if existing:
            parent = existing[0]
            continue

        child = parent.add_project()
        child.description = step
        child.save()

        parent = child

    return parent


def project_pool() -> List[Candidate]:
    """
    Every project as a completion candidate, read once when the window opens

    Each carries the project itself as `key`, since two projects can share
    the path a completion writes.
    """

    return [
        Candidate(
            steps=project_steps(project),
            has_children=bool(project.projects),
            key=project,
        )
        for project in Project.all()
    ]


def project_steps(project: Project) -> Tuple[str, ...]:
    """A project's path from the top of the tree, the root excluded"""

    steps: List[str] = []
    node: Optional[Project] = project

    while node is not None and not node.is_root:
        steps.append(node.description.strip())
        node = node.parent_project

    return tuple(reversed(steps))


def project_display(name: str) -> str:
    """A typed project name written the way the app writes a project path"""

    return PATH_SEPARATOR.join(split_path(name))


class ProjectCompletion:
    """
    The list of projects under a typed line, and the keys that walk it

    The host screen provides `self._input`, `theme`, `_faded` and `_redraw`,
    and says where the name sits (`_completion_token`) and how a finished one
    is written back (`LEAF_TRAILING`, `_written`).
    """

    # Appended after a completed project with no children
    LEAF_TRAILING = ""

    def _init_completion(self) -> None:
        self._pool: List[Candidate] = []

        # The name being completed and its matches. Frozen while the list is
        # walked, since walking rewrites the very line they came from.
        self._token: Optional[Token] = None
        self._matches: List[Candidate] = []

        # Where in the line the next completion is written
        self._span: Tuple[int, int] = (0, 0)

        # The match on offer (-1: none yet) and the first one on screen
        self._index = -1
        self._offset = 0

        # Whether tab/arrows are cycling the list rather than narrowing it
        self._walking = False

        # Hidden by escape until the name is typed into again
        self._hidden = False

        # The project last completed into the line, and the text written for
        # it: the name alone may match several projects
        self._picked: Optional[Project] = None
        self._picked_text = ""

    def load_projects(self) -> None:
        self._pool = project_pool()

    @property
    def suggesting(self) -> bool:
        """Whether the list of projects is up"""

        return bool(self._matches) and not self._hidden

    def hide_suggestions(self) -> None:
        self._hidden = True
        self._redraw()

    def picked_among(self, found: Sequence[Project]) -> Optional[Project]:
        """
        The project picked from the list, if the typed name still finds it

        A pick settles an ambiguous name, and is the only way to choose a
        same-named project at the top of the tree.
        """

        if self._picked is None or self._picked not in found:
            return None

        return self._picked

    # ------------------------------------------------------------------
    # Keys
    # ------------------------------------------------------------------

    def handle_completion_key(self, key: str) -> bool:
        """
        Whether the list took the key. Tab is always swallowed, even with
        nothing to complete: a literal tab in the line is never wanted.
        """

        if self.suggesting:
            if key in ("tab", "down", "ctrl+n"):
                self._complete(1, agreed=key == "tab")
                return True

            if key in ("shift+tab", "up", "ctrl+p"):
                self._complete(-1, agreed=key == "shift+tab")
                return True

        return key in ("tab", "shift+tab")

    # ------------------------------------------------------------------
    # Completing
    # ------------------------------------------------------------------

    def _resuggest(self) -> None:
        """Recomputes the token and its matches; run after every typed key"""

        self._walking = False
        self._index = -1
        self._offset = 0
        self._token = self._completion_token()

        # A pick stands until the name it was written as is edited
        if self._token is not None and self._token.text != self._picked_text:
            self._picked = None
            self._picked_text = ""

        if self._token is None:
            self._matches = []
            return

        self._span = (self._token.start, self._token.end)
        self._matches = matching(self._token, self._pool)

    def _complete(self, step: int, agreed: bool) -> None:
        """
        Tab first extends to the prefix all matches share, then cycles through
        them one at a time. The arrows skip straight to cycling.
        """

        assert self._token is not None

        if not self._walking and agreed:
            if len(self._matches) == 1:
                self._accept(self._matches[0])
                return

            grown = common_prefix([match.name for match in self._matches])

            if len(grown) > len(self._token.partial):
                self._write(extended(self._token, grown))
                self._resuggest()
                self._completed()
                return

        # From here the list stands still while its entries are written in
        self._walking = True

        if self._index < 0:
            self._index = 0 if step > 0 else len(self._matches) - 1
        else:
            self._index = (self._index + step) % len(self._matches)

        candidate = self._matches[self._index]

        self._show(self._index)

        # The leaf trailer is withheld: it would move the cursor out of the
        # name being cycled
        self._write(
            completion(self._token, candidate, self._pool),
            PATH_SEPARATOR if candidate.has_children else "",
        )

        self._remember(candidate)
        self._completed()

    def _accept(self, candidate: Candidate) -> None:
        """
        Writes the whole project in. One with children is left open with a
        trailing separator, like a directory at a shell prompt.
        """

        assert self._token is not None

        path = completion(self._token, candidate, self._pool)
        trailing = PATH_SEPARATOR if candidate.has_children else self.LEAF_TRAILING

        self._write(path, trailing)
        self._resuggest()

        # After the resuggest, which drops the pick made under the old name
        self._remember(candidate)
        self._completed()

    def _remember(self, candidate: Candidate) -> None:
        # Read back off the line so it matches what the next keystroke sees
        token = self._completion_token()

        self._picked = candidate.key
        self._picked_text = token.text if token is not None else ""

    def _write(self, path: str, trailing: str = "") -> None:
        start, end = self._span
        text = self._written(path, trailing)

        self._input.replace(start, end, text)
        self._span = (start, start + len(text))

    def _show(self, index: int) -> None:
        """Scrolls the list so the match on offer is visible"""

        if index < self._offset:
            self._offset = index
        elif index >= self._offset + MAX_SUGGESTIONS:
            self._offset = index - MAX_SUGGESTIONS + 1

    # ------------------------------------------------------------------
    # Drawing
    # ------------------------------------------------------------------

    def _suggestions(self) -> List[RenderableType]:
        """The matching projects as full paths, under the line"""

        if not self.suggesting:
            return []

        window = self._matches[self._offset : self._offset + MAX_SUGGESTIONS]

        # Full panel width, so the highlighted row is a band
        table = Table.grid(expand=True, padding=(0, 1))
        table.add_column(width=1)
        table.add_column(ratio=1, no_wrap=True, overflow="ellipsis")

        for offset, candidate in enumerate(window, start=self._offset):
            table.add_row(
                PROJECT_ICON,
                PATH_SEPARATOR.join(candidate.steps),
                style=self._match_style(offset),
            )

        rows: List[RenderableType] = [Text(), table]

        left = len(self._matches) - self._offset - len(window)

        if left > 0:
            rows.append(self._faded(MORE.format(left)))

        return rows

    def _match_style(self, index: int) -> Style:
        if index != self._index:
            return Style(color=self.theme.foreground2)

        return Style(color=self.theme.primary, bgcolor=self.theme.background3)

    # ------------------------------------------------------------------
    # What the screen answers
    # ------------------------------------------------------------------

    def _completion_token(self) -> Optional[Token]:
        """The name being completed, or None when the line asks for none"""

        raise NotImplementedError  # pragma: no cover

    def _written(self, path: str, trailing: str) -> str:
        """A completed path as written into the line; quoted by default"""

        return written(path, trailing)

    def _completed(self) -> None:
        """Runs after a completion is written into the line"""

        self._redraw()

    def _redraw(self) -> None:
        raise NotImplementedError  # pragma: no cover
