"""
The command line: a whole task typed in one line, over the top of the app

Every other way of adding a task in dooit is a row and a column at a time --
open the project, add the todo, name it, then type a date into the column
beside it. This is the same task said in one breath, from wherever you happen
to be standing, and it never moves the cursor off what you were looking at.

The line is read by `dooit.utils.quick_add`; what is left here is the panel it
is typed into, what the panel says about the line as it is being typed, and
the one place the task is actually written to the database.

The one field that is answered rather than merely read back is the project: a
project lives in a tree and is written like a path, so a half typed `#name` is
finished the way a filename is finished at a shell prompt. The working out is
`dooit.utils.project_complete`; the list under the line, and the keys that
walk it, are here.
"""

from typing import List, NamedTuple, Optional, Sequence, Tuple

from rich.console import Group, RenderableType
from rich.style import Style
from rich.table import Table
from rich.text import Text
from textual import events
from textual.app import ComposeResult
from textual.screen import ModalScreen
from textual.widgets import Static

from todooit.api import Project, Todo
from todooit.api.fixed_projects import PATH_SEPARATOR as PATH_DISPLAY
from todooit.api.theme import DooitThemeBase
from todooit.ui.widgets.inputs._input import Input
from todooit.utils import blend, day_label
from todooit.utils.project_complete import (
    Candidate,
    Token,
    common_prefix,
    completion,
    extended,
    find_token,
    matching,
    written,
)
from todooit.utils.quick_add import (
    DUE_MARKER,
    LABEL_MARKER,
    PATH_SEPARATOR,
    PROJECT_MARKER,
    TAG_MARKER,
    QuickAddError,
    QuickAddSpec,
    parse_quick_add,
    split_path,
)

from .base import BaseScreen

# What the panel is titled, in the border, the way the note window is
PANEL_TITLE = "Add task"

# The glyph the line is typed after. Nothing is being run, so it is a prompt
# rather than a colon: the line is a sentence, and this is where it starts.
PROMPT = "❯ "

# The folder the projects pane draws its rows with, so the project a task is
# going into is recognisably the row over there
PROJECT_ICON = "󰉋"

# The calendar a date still to come is marked with in the date columns
DATE_ICON = "󰃰"

# What sits between two things the line was read as. Narrow, because a line
# that fills every field has six of them to fit on the row: they are told
# apart by their colours and their icons rather than by the space around them
CHIP_GAP = "  "

# How far the things the line has not said are pulled towards the background:
# the project nobody named, and the legend under the panel
IMPLIED_FADE = 0.45

# What is asked when the line names a project nobody has. Worded the way every
# other y/N in dooit is, so the answer is the one already known. Drawn as text
# rather than as markup, so the brackets need no escaping here.
CREATE_PROMPT = "No project {} — create it? [y/N]"

# The legend, in the order the markers are worth learning in. Tighter gaps
# than the preview above it, so the whole of it fits on the one line
HINT_GAP = "  "
HINT = HINT_GAP.join(
    (
        f"{PROJECT_MARKER}project",
        f"{LABEL_MARKER}label",
        "p1-p3",
        "e1-e3",
        "date",
        f"{DUE_MARKER}date",
        "   esc cancel",
        "enter add",
    )
)

# What the legend says instead while the question above stands, since neither
# of the keys it normally names does what it says any more
CREATE_HINT = "y  create it and add the task      any other key  back to the line"

# And what it says while the list of projects is up, which is the one time
# tab and the arrows mean something other than what they usually do here
SUGGEST_HINT = HINT_GAP.join(
    (
        "tab complete",
        "↑↓ pick",
        "esc close list",
    )
)

# How many projects the list offers at once. The rest are still there -- the
# cursor scrolls the window over them -- but the panel sits over the app and
# a list long enough to bury it is answering a question nobody asked.
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

    Read once when the overlay opens rather than at each keystroke: the tree
    cannot change underneath a line that is still being typed, and the only
    thing here that does add a project closes the overlay as it goes.
    """

    return [
        Candidate(steps=project_steps(project), has_children=bool(project.projects))
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


class QuickAdded(NamedTuple):
    """
    What the overlay hands back when a task was actually added
    """

    todo: Todo
    # Whether a project had to be built to put it in, which the projects pane
    # has to be told about: the row is new, and may be nested out of sight
    project_created: bool


class QuickAddScreen(BaseScreen, ModalScreen):
    """
    The panel the line is typed into, over a dimmed copy of the app

    An overlay rather than another bar: the line says everything about a task
    at once, and the answer it is given -- which project, which day -- is
    worth two lines and a border of its own. The app stays visible behind it,
    since what is being added is being added to what is on screen.
    """

    def __init__(self, default_project: Optional[Project] = None) -> None:
        super().__init__()

        # Where a task goes when the line does not say: the project the panes
        # were opened on. There is none when that was a fixed project, and
        # then the line has to name one itself.
        self.default_project = default_project

        self._input = Input()
        self._input.is_editing = True

        # The last thing that could not be read, shown in place of the
        # preview until the next keystroke
        self._warning = ""

        # A line that named a project nobody has, held while the question of
        # whether to build one stands. The line is settled either way by the
        # next key, so nothing else can arrive in the meantime.
        self._pending: Optional[QuickAddSpec] = None

        # Every project, for the list under the line to be drawn from
        self._pool: List[Candidate] = []

        # The `#name` being typed and what it could still mean. Held rather
        # than worked out afresh each time it is wanted, because walking the
        # list writes into the very line it was built from: once the walking
        # has started, the list is the one it started on and the token is the
        # one that was typed, not the one tab has since put there.
        self._token: Optional[Token] = None
        self._matches: List[Candidate] = []

        # Where in the line the next completion is written, which moves out
        # from under the token as longer names are tried in it
        self._span: Tuple[int, int] = (0, 0)

        # Which match is being offered, counted through the whole list. -1 is
        # a list nobody has walked into yet, which is how it starts: the line
        # says what it says, and no project has been put into it.
        self._index = -1
        self._offset = 0

        # Whether the list is being walked rather than typed at. While it is,
        # the matches stand still under the cursor instead of being narrowed
        # down by the name tab has just written into the line.
        self._walking = False

        # A list escape has put away. It stays away until the name it was
        # offering against is typed into again, since reopening under the
        # next keystroke would be ignoring what escape was for.
        self._hidden = False

    @property
    def theme(self) -> DooitThemeBase:
        return self.api.vars.theme

    @property
    def panel(self) -> Static:
        return self.query_one("#quick-add-panel", Static)

    @property
    def hint(self) -> Static:
        return self.query_one("#quick-add-hint", Static)

    def compose(self) -> ComposeResult:
        yield Static(id="quick-add-panel")
        yield Static(HINT, id="quick-add-hint")

    def on_mount(self) -> None:
        self.panel.border_title = PANEL_TITLE
        self._pool = project_pool()
        self._redraw()

    @property
    def suggesting(self) -> bool:
        """
        Whether the list of projects is up, which is what lends tab its meaning
        """

        return bool(self._matches) and not self._hidden and self._pending is None

    # ------------------------------------------------------------------
    # Typing
    # ------------------------------------------------------------------

    async def handle_key(self, event: events.Key) -> bool:
        # Every key belongs to the line, including the ones the app binds
        # elsewhere: this is a text field, and `q` is a letter in it
        event.stop()

        key = self.resolve_key(event)

        # A question about building a project takes the whole keyboard while
        # it stands, so that a `y` is an answer to it and not a letter
        if self._pending is not None:
            self._answer_create(key)
            return True

        # While the list of projects is up it owns the keys that walk a list,
        # and the escape that would otherwise throw the whole line away. None
        # of them mean anything else here: tab has no business in a one line
        # sentence, and nothing in the panel scrolls.
        if self.suggesting:
            if key in ("tab", "down", "ctrl+n"):
                self._complete(1, agreed=key == "tab")
                return True

            if key in ("shift+tab", "up", "ctrl+p"):
                self._complete(-1, agreed=key == "shift+tab")
                return True

            if key == "escape":
                self._hidden = True
                self._redraw()
                return True

        # Tab belongs to the completion even when there is nothing to
        # complete. It is the one key here that would otherwise put something
        # into the line that cannot be seen in it: a tab character in a one
        # line sentence is never what was meant, and a name nobody has is
        # exactly when it would be typed by mistake.
        if key in ("tab", "shift+tab"):
            return True

        if key == "escape":
            self.dismiss(None)
            return True

        if key == "enter":
            self._submit()
            return True

        self._input.keypress(key)

        # A warning is about the line as it was; the moment it is typed into
        # again it is about nothing. A list put away is about the name as it
        # was, and so is a list being walked through: both are answers to a
        # question the keystroke has just asked again.
        self._warning = ""
        self._hidden = False
        self._resuggest()
        self._redraw()

        return True

    # ------------------------------------------------------------------
    # Completing the project
    # ------------------------------------------------------------------

    def _resuggest(self) -> None:
        """
        Works out what the line is asking to be completed, and with what

        Run after every keystroke that is not itself a completion, so the
        list under the line is always about the name as it stands now.
        """

        self._walking = False
        self._index = -1
        self._offset = 0

        self._token = (
            None
            if self._pending is not None
            else find_token(self._input.value, self._input.cursor_position)
        )

        if self._token is None:
            self._matches = []
            return

        self._span = (self._token.start, self._token.end)
        self._matches = matching(self._token, self._pool)

    def _complete(self, step: int, agreed: bool) -> None:
        """
        Takes the line as far towards a project as the matches will carry it

        Tab does what it does at a shell prompt: first as much of the name as
        every match agrees on, and then, once there is nothing left they
        agree on, one match at a time. The arrows skip the agreeing and go
        straight to walking the list, which is the only thing they are for.
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
                self._redraw()
                return

        # Nothing left to agree on, so the matches are offered one at a time.
        # The list stands still from here: tab is writing into the line it
        # was built from, and narrowing it under its own answers would leave
        # one match after the first press.
        self._walking = True

        if self._index < 0:
            self._index = 0 if step > 0 else len(self._matches) - 1
        else:
            self._index = (self._index + step) % len(self._matches)

        candidate = self._matches[self._index]

        self._show(self._index)

        # Punctuated the way it would be if it were taken, so that walking
        # the list shows the shape of each match and not just its name --
        # except for the space that ends the field, which is withheld: it
        # would put the cursor outside the very name being walked through,
        # and the next press would have nothing left to walk.
        self._write(
            completion(self._token, candidate, self._pool),
            PATH_SEPARATOR if candidate.has_children else "",
        )

        self._warning = ""
        self._redraw()

    def _accept(self, candidate: Candidate) -> None:
        """
        Puts the whole project in, and says whether there is more to type

        A project with children is left open the way a directory is at a
        prompt: the separator is already there, and the list underneath has
        turned into what is inside it. One with none is the whole answer, and
        the space after it is where the task itself starts.
        """

        assert self._token is not None

        path = completion(self._token, candidate, self._pool)

        self._write(path, PATH_SEPARATOR if candidate.has_children else " ")
        self._warning = ""
        self._resuggest()
        self._redraw()

    def _write(self, path: str, trailing: str = "") -> None:
        """
        Swaps what was typed after the `#` for the project it is turning into
        """

        start, end = self._span
        text = written(path, trailing)

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

    def _redraw(self) -> None:
        self.panel.update(
            Group(self._line(), self._preview(), *self._suggestions())
        )

        if self._pending:
            self.hint.update(CREATE_HINT)
        elif self.suggesting:
            self.hint.update(SUGGEST_HINT)
        else:
            self.hint.update(HINT)

    def _suggestions(self) -> List[RenderableType]:
        """
        The projects the half typed name could still mean, under the line

        Drawn as the paths they are rather than as bare names: the whole
        point of the list is the two projects called `api`, and a name on its
        own would show them as the same row twice.
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

    def _line(self) -> Text:
        # The buffer draws itself rather than being handed over as a string,
        # so that a selection made in it is highlighted here too; the line's
        # own colour goes underneath, where the highlight overrides it
        buffer = self._input.render_editing(self.theme)
        buffer.style = Style(color=self.theme.foreground3)

        return Text(PROMPT, style=Style(color=self.theme.primary, bold=True)) + buffer

    # ------------------------------------------------------------------
    # What the line has been read as
    # ------------------------------------------------------------------

    def _preview(self) -> Text:
        """
        The fields the line has given up so far, or the warning it earned

        A line still being typed is half a line, and half a line is not an
        error: while it cannot be read at all the row simply stays empty, and
        only pressing enter turns what is wrong with it into a warning.
        """

        if self._pending is not None:
            # A question rather than a complaint, and coloured as one: nothing
            # is wrong with the line, there is only something it takes for
            # granted that is not there yet
            return Text(
                CREATE_PROMPT.format(project_display(self._pending.project)),
                style=Style(color=self.theme.yellow, bold=True),
            )

        if self._warning:
            return Text(self._warning, style=Style(color=self.theme.red, bold=True))

        try:
            spec = parse_quick_add(self._input.value)
        except QuickAddError:
            return Text()

        return Text(CHIP_GAP).join(self._chips(spec))

    def _chips(self, spec: QuickAddSpec) -> List[Text]:
        theme = self.theme
        chips = [self._project_chip(spec)]

        for label in spec.labels:
            chips.append(
                Text(f"{TAG_MARKER}{label}", style=Style(color=theme.magenta))
            )

        for name, value in (("p", spec.priority), ("e", spec.effort)):
            if value:
                chips.append(
                    Text(
                        f"{name}{value}",
                        style=Style(color=theme.foreground2, bold=True),
                    )
                )

        # The two dates side by side, in the order the row draws them, with
        # the deadline named: they are written the same way and read the same
        # way, so what tells them apart has to be said rather than shown
        for lead, date in (("", spec.scheduled), (DUE_MARKER.strip("="), spec.due)):
            if date is None:
                continue

            when = day_label(date)

            if date.hour or date.minute:
                when += date.strftime(" (%H:%M)")

            chips.append(
                Text(
                    f"{lead} {DATE_ICON} {when}".strip(),
                    style=Style(color=theme.yellow),
                )
            )

        return [chip for chip in chips if chip.plain]

    def _project_chip(self, spec: QuickAddSpec) -> Text:
        """
        Where the task is going, said before it goes there

        A project that was named and cannot be found is drawn in red as it is
        typed, so the line is not written out and turned down afterwards. One
        that was never named is the pane's own, and is drawn as the assumption
        it is rather than as something the line said.
        """

        theme = self.theme

        if not spec.project:
            if self.default_project is None:
                # Nothing to fall back on: the panes were opened on a fixed
                # project, which owns none of what it gathers. The line has to
                # name one, and the chip stands where that name goes.
                return Text(
                    f"{PROJECT_ICON} {PROJECT_MARKER}project",
                    style=Style(color=theme.red, dim=True),
                )

            faded = blend(theme.foreground1, theme.background2, IMPLIED_FADE)
            return Text(
                f"{PROJECT_ICON} {self.default_project.description}",
                style=Style(color=faded),
            )

        found = find_projects(spec.project)
        color = theme.primary if len(found) == 1 else theme.red
        name = found[0].description if len(found) == 1 else spec.project

        return Text(f"{PROJECT_ICON} {name}", style=Style(color=color))

    # ------------------------------------------------------------------
    # Adding
    # ------------------------------------------------------------------

    def _submit(self) -> None:
        """
        Writes the task out, or says what stopped it and hands the line back

        A line that could not be read is thrown away rather than left to be
        corrected: it is one line, retyping it is quicker than finding the
        word in it that was wrong, and what the warning says is what to do
        differently the second time.
        """

        try:
            spec = parse_quick_add(self._input.value)
            project = self._target(spec)
        except QuickAddError as error:
            self._reject(str(error))
            return

        # A name nobody answers to is not a mistake in the line; it is a
        # project that does not exist yet, and the only one who can say
        # whether it should is the one who typed it
        if project is None:
            self._pending = spec
            self._redraw()
            return

        self.dismiss(QuickAdded(self._create(spec, project), False))

    def _answer_create(self, key: str) -> None:
        """
        Builds the project and files the task in it, or leaves both alone

        Anything but a `y` puts the line back exactly as it was typed, rather
        than clearing it the way a line that could not be read is cleared:
        what was wrong here is one word of it, and correcting that word is
        quicker than saying the whole thing again.
        """

        spec, self._pending = self._pending, None
        assert spec is not None

        if key.lower() != "y":
            self._redraw()
            return

        project = build_project(split_path(spec.project))
        self.dismiss(QuickAdded(self._create(spec, project), True))

    def _target(self, spec: QuickAddSpec) -> Optional[Project]:
        """
        The project the task is filed under, named or assumed

        None where the line named one that is nobody's, which is a question to
        put rather than an answer to give.
        """

        if not spec.project:
            if self.default_project is None:
                raise QuickAddError(
                    f"Say which project, with {PROJECT_MARKER}name"
                )

            return self.default_project

        found = find_projects(spec.project)

        if len(found) > 1:
            raise QuickAddError(
                f"More than one {spec.project} — "
                f"try {PROJECT_MARKER}parent{PATH_SEPARATOR}{spec.project}"
            )

        return found[0] if found else None

    @staticmethod
    def _create(spec: QuickAddSpec, project: Project) -> Todo:
        todo = project.add_todo()

        todo.description = spec.described
        todo.scheduled = spec.scheduled
        todo.due = spec.due
        todo.priority = spec.priority
        todo.effort = spec.effort
        todo.save()

        return todo

    def _reject(self, warning: str) -> None:
        self._warning = warning
        self._input.clear_input()
        self._redraw()
