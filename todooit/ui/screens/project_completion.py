"""
Finishing a half typed project name, and the list of what it could still be

Two windows ask for a project by name. In the one line task entry the name is
one field of a sentence, marked out with a `#`; in the move window it is the
whole line and there is nothing else on it. Either way it is finished the way
a path is finished at a shell prompt -- as much of the name as every match
agrees on, and then, once they stop agreeing, one match at a time -- and the
same list of what is still possible is drawn underneath.

What differs between the two is only where in the line the name sits and how a
finished one is punctuated, which is what the hooks at the foot of the mixin
are for. The working out is `dooit.utils.project_complete`, which knows nothing
about the database; which projects there are is settled here.
"""

from typing import List, Optional, Sequence, Tuple

from rich.console import RenderableType
from rich.style import Style
from rich.table import Table
from rich.text import Text

from todooit.api import Project
from todooit.api.fixed_projects import PATH_SEPARATOR as PATH_DISPLAY
from todooit.utils import blend
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

# The folder the projects pane draws its rows with, so a project named in a
# window over the app is recognisably the row over there
PROJECT_ICON = "󰉋"

# How far the things a line has not said are pulled towards the background
IMPLIED_FADE = 0.45

# How many projects the list offers at once. The rest are still there -- the
# cursor scrolls the window over them -- but the panel sits over the app and a
# list long enough to bury it is answering a question nobody asked.
MAX_SUGGESTIONS = 8

# What is said under the last row when the list is longer than the window,
# since a window with no edge to it looks like the whole answer
MORE = "…and {} more"


def find_projects(name: str) -> List[Project]:
    """
    Every project a typed name could mean

    A name on its own is looked for at any depth, since that is how a project
    is spoken about; a path (`work/api`) is matched from the bottom up, which
    is what tells two projects sharing a name apart without having to spell
    out the whole way down from the root.
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
    """
    Makes the project a path names, and every project above it that is missing

    Read from the root down rather than looked for at any depth, which is what
    `find_projects` does: a name that was not found anywhere is a new project,
    and where a new project goes has to be somewhere that can be pointed at.
    """

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
    Every project there is, as something a half typed name could become

    Read once when the window opens rather than at each keystroke: the tree
    cannot change underneath a line that is still being typed, and the only
    thing here that does add a project closes the window as it goes.

    Each carries the project it was made from, so that picking a match out of
    the list is picking the project itself and not merely its path: two
    projects can share the path a completion writes, and only the list knows
    which of them was walked to.
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
    """
    A project as the path down to it, from the top of the tree

    The root is not a step: it is the tree itself rather than a project
    anybody files anything under, and nobody types it.
    """

    steps: List[str] = []
    node: Optional[Project] = project

    while node is not None and not node.is_root:
        steps.append(node.description.strip())
        node = node.parent_project

    return tuple(reversed(steps))


def project_display(name: str) -> str:
    """
    A typed project name written the way the app writes a project path
    """

    return PATH_DISPLAY.join(split_path(name))


class ProjectCompletion:
    """
    The list of projects under a typed line, and the keys that walk it

    Mixed into a screen that types into an `Input` at `self._input`, draws
    itself with `_redraw`, and carries the `theme` every screen here has. The
    screen says where in the line the name sits (`_completion_token`) and how a
    finished one is written back into it (`LEAF_TRAILING`, `_written`);
    everything else -- what still matches, which match is being offered, how
    far the window has scrolled -- is held here.
    """

    # What is put after a completed project that has nothing inside it. The
    # task entry goes on to the task itself, so the field is closed off with a
    # space; a window whose whole line is the name closes it with nothing.
    LEAF_TRAILING = ""

    def _init_completion(self) -> None:
        # Every project, for the list under the line to be drawn from
        self._pool: List[Candidate] = []

        # The name being typed and what it could still mean. Held rather than
        # worked out afresh each time it is wanted, because walking the list
        # writes into the very line it was built from: once the walking has
        # started, the list is the one it started on and the token is the one
        # that was typed, not the one tab has since put there.
        self._token: Optional[Token] = None
        self._matches: List[Candidate] = []

        # Where in the line the next completion is written, which moves out
        # from under the token as longer names are tried in it
        self._span: Tuple[int, int] = (0, 0)

        # Which match is being offered, counted through the whole list. -1 is a
        # list nobody has walked into yet, which is how it starts: the line
        # says what it says, and no project has been put into it.
        self._index = -1
        self._offset = 0

        # Whether the list is being walked rather than typed at. While it is,
        # the matches stand still under the cursor instead of being narrowed
        # down by the name tab has just written into the line.
        self._walking = False

        # A list escape has put away. It stays away until the name it was
        # offering against is typed into again, since reopening under the next
        # keystroke would be ignoring what escape was for.
        self._hidden = False

        # The project a completion last put into the line, and the name it
        # wrote it as. Held because the name need not say which project it
        # means: two of them can answer to it, and the one that was picked out
        # of the list is the one that was meant.
        self._picked: Optional[Project] = None
        self._picked_text = ""

    def load_projects(self) -> None:
        """Reads the tree in, once, as the window opens"""

        self._pool = project_pool()

    @property
    def suggesting(self) -> bool:
        """
        Whether the list of projects is up, which is what lends tab its meaning
        """

        return bool(self._matches) and not self._hidden

    def hide_suggestions(self) -> None:
        """Puts the list away until the name is typed into again"""

        self._hidden = True
        self._redraw()

    def picked_among(self, found: Sequence[Project]) -> Optional[Project]:
        """
        Which of the projects a name found is the one picked out of the list

        A name two projects answer to is not ambiguous when it was chosen
        rather than typed: the list showed both, one of them was walked to,
        and there is nothing left to ask. It is the only way to say which of
        two same-named projects is meant when one of them sits at the top of
        the tree, since a path can name that one by nothing but its name.

        Checked against what the name finds rather than taken on its own, so
        that a pick the line has since been rewritten past settles nothing.
        """

        if self._picked is None or self._picked not in found:
            return None

        return self._picked

    # ------------------------------------------------------------------
    # Keys
    # ------------------------------------------------------------------

    def handle_completion_key(self, key: str) -> bool:
        """
        Whether the list took the key, and what it did with it

        Tab belongs to the completion even when there is nothing to complete.
        It is the one key here that would otherwise put something into the line
        that cannot be seen in it: a tab character in a typed line is never
        what was meant, and a name nobody has is exactly when it would be
        pressed by mistake.
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
        """
        Works out what the line is asking to be completed, and with what

        Run after every keystroke that is not itself a completion, so the list
        under the line is always about the name as it stands now.
        """

        self._walking = False
        self._index = -1
        self._offset = 0
        self._token = self._completion_token()

        # A pick stands while the name it was written into still says what it
        # said. The line can go on to talk about other things -- the cursor
        # leaves the name behind, and the pick is still the answer to it --
        # but typing into the name itself is asking the question again.
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
        Takes the line as far towards a project as the matches will carry it

        Tab does what it does at a shell prompt: first as much of the name as
        every match agrees on, and then, once there is nothing left they agree
        on, one match at a time. The arrows skip the agreeing and go straight
        to walking the list, which is the only thing they are for.
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

        # Nothing left to agree on, so the matches are offered one at a time.
        # The list stands still from here: tab is writing into the line it was
        # built from, and narrowing it under its own answers would leave one
        # match after the first press.
        self._walking = True

        if self._index < 0:
            self._index = 0 if step > 0 else len(self._matches) - 1
        else:
            self._index = (self._index + step) % len(self._matches)

        candidate = self._matches[self._index]

        self._show(self._index)

        # Punctuated the way it would be if it were taken, so that walking the
        # list shows the shape of each match and not just its name -- except
        # for whatever closes the name off, which is withheld: it would put the
        # cursor outside the very name being walked through, and the next press
        # would have nothing left to walk.
        self._write(
            completion(self._token, candidate, self._pool),
            PATH_SEPARATOR if candidate.has_children else "",
        )

        self._remember(candidate)
        self._completed()

    def _accept(self, candidate: Candidate) -> None:
        """
        Puts the whole project in, and says whether there is more to type

        A project with children is left open the way a directory is at a
        prompt: the separator is already there, and the list underneath has
        turned into what is inside it. One with none is the whole answer.
        """

        assert self._token is not None

        path = completion(self._token, candidate, self._pool)
        trailing = PATH_SEPARATOR if candidate.has_children else self.LEAF_TRAILING

        self._write(path, trailing)
        self._resuggest()

        # After the resuggest, which is about the name as the line now spells
        # it and drops whatever was picked under the old one
        self._remember(candidate)
        self._completed()

    def _remember(self, candidate: Candidate) -> None:
        """
        Holds on to the project a completion has just written into the line

        Read back off the line rather than worked out from the path that was
        written, so that what is remembered is the name as the next keystroke
        will find it -- quotes taken off, and the steps above it included.
        """

        token = self._completion_token()

        self._picked = candidate.key
        self._picked_text = token.text if token is not None else ""

    def _write(self, path: str, trailing: str = "") -> None:
        """
        Swaps the half typed name for the project it is turning into
        """

        start, end = self._span
        text = self._written(path, trailing)

        self._input.replace(start, end, text)
        self._span = (start, start + len(text))

    def _show(self, index: int) -> None:
        """
        Pulls the window along so the match being offered is inside it
        """

        if index < self._offset:
            self._offset = index
        elif index >= self._offset + MAX_SUGGESTIONS:
            self._offset = index - MAX_SUGGESTIONS + 1

    # ------------------------------------------------------------------
    # Drawing
    # ------------------------------------------------------------------

    def _suggestions(self) -> List[RenderableType]:
        """
        The projects the half typed name could still mean, under the line

        Drawn as the paths they are rather than as bare names: the whole point
        of the list is the two projects called `api`, and a name on its own
        would show them as the same row twice.
        """

        if not self.suggesting:
            return []

        window = self._matches[self._offset : self._offset + MAX_SUGGESTIONS]

        # Filled to the width of the panel rather than to the longest row, so
        # that the match being offered is a band across the list instead of a
        # patch the length of its own name
        table = Table.grid(expand=True, padding=(0, 1))
        table.add_column(width=1)
        table.add_column(ratio=1, no_wrap=True, overflow="ellipsis")

        for offset, candidate in enumerate(window, start=self._offset):
            table.add_row(
                PROJECT_ICON,
                PATH_DISPLAY.join(candidate.steps),
                style=self._match_style(offset),
            )

        rows: List[RenderableType] = [Text(), table]

        left = len(self._matches) - self._offset - len(window)

        if left > 0:
            rows.append(
                Text(
                    MORE.format(left),
                    style=Style(
                        color=blend(
                            self.theme.foreground1,
                            self.theme.background2,
                            IMPLIED_FADE,
                        )
                    ),
                )
            )

        return rows

    def _match_style(self, index: int) -> Style:
        """
        How a row is drawn: the one being offered stands out, the rest do not
        """

        if index != self._index:
            return Style(color=self.theme.foreground2)

        return Style(color=self.theme.primary, bgcolor=self.theme.background3)

    # ------------------------------------------------------------------
    # What the screen answers
    # ------------------------------------------------------------------

    def _completion_token(self) -> Optional[Token]:
        """
        The name being completed and where in the line it sits, or None when
        the line is not asking for a project at all
        """

        raise NotImplementedError  # pragma: no cover

    def _written(self, path: str, trailing: str) -> str:
        """
        A completed path as it is written back into the line

        Quoted by default, which is what a name with a space in it needs to
        survive being read back out of a line that says other things too.
        """

        return written(path, trailing)

    def _completed(self) -> None:
        """
        Run once a completion has been written into the line

        A hook rather than a plain `_redraw` so that a screen showing what the
        line has been read as can drop whatever it was complaining about: the
        complaint was about the name the completion has just replaced.
        """

        self._redraw()

    def _redraw(self) -> None:
        raise NotImplementedError  # pragma: no cover
