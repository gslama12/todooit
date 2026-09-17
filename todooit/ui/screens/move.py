"""
The move window: the project a task is to be filed under, typed in one line

A task ends up in the wrong project often enough, and until now the only way
out of one was to retype it in the right one. What was missing is the same
thing the one line entry already knows how to ask -- which project -- so this
asks only that, over the app, from wherever the cursor happens to be standing.

The line is nothing but the project: there are no fields to pick apart and no
marker to open one with, so the whole of it is the name and it is completed
from the first letter. That completion is `.project_completion`, shared with
the one line entry; the panel, what it says about the task being moved, and
the move itself are here.
"""

from typing import NamedTuple, Optional

from rich.console import Group
from rich.style import Style
from rich.text import Text
from textual import events
from textual.app import ComposeResult
from textual.screen import ModalScreen
from textual.widgets import Static

from todooit.api import Project, Todo
from todooit.api.fixed_projects import owning_project, project_path
from todooit.api.theme import DooitThemeBase
from todooit.ui.widgets.inputs._input import Input
from todooit.utils import blend
from todooit.utils.project_complete import Token
from todooit.utils.quick_add import PATH_SEPARATOR

from .base import BaseScreen
from .project_completion import (
    IMPLIED_FADE,
    PROJECT_ICON,
    ProjectCompletion,
    find_projects,
    project_display,
)

# What the panel is titled, in the border, the way the one line entry is
PANEL_TITLE = "Move task"

# The glyph the name is typed after, the same one every line typed over the
# app starts with
PROMPT = "❯ "

# The arrow between where the task is now and where it is going. Drawn rather
# than said, since both ends of it are already named
ARROW = "→"

# What stands in for the project a task has no name for: one lifted out of a
# project that was deleted, which is only ever in the Bin
NOWHERE = "nowhere"

HINT_GAP = "  "
HINT = HINT_GAP.join(
    (
        "tab complete",
        "↑↓ pick",
        "esc cancel",
        "enter move",
    )
)


class Moved(NamedTuple):
    """
    What the window hands back once the task has actually been moved
    """

    todo: Todo
    project: Project


class MoveScreen(ProjectCompletion, BaseScreen, ModalScreen):
    """
    The panel the project is typed into, over a dimmed copy of the app

    An overlay rather than a bar, for the same reason the one line entry is
    one: what is being typed is a question about the tree, and the list of
    answers to it has to go somewhere. The app stays visible behind it, since
    the project the task is about to land in is a row over there.
    """

    def __init__(self, todo: Todo) -> None:
        super().__init__()

        # The task being moved, held rather than looked up again: the panes
        # are behind the window and the cursor in them can no longer be asked
        self.todo = todo

        self._input = Input()
        self._input.is_editing = True

        # The last name that could not be answered, shown under the line until
        # the next keystroke
        self._warning = ""

        self._init_completion()

    @property
    def theme(self) -> DooitThemeBase:
        return self.api.vars.theme

    @property
    def panel(self) -> Static:
        return self.query_one("#move-panel", Static)

    @property
    def hint(self) -> Static:
        return self.query_one("#move-hint", Static)

    def compose(self) -> ComposeResult:
        yield Static(id="move-panel")
        yield Static(HINT, id="move-hint")

    def on_mount(self) -> None:
        self.panel.border_title = PANEL_TITLE
        self.load_projects()

        # Worked out before anything is typed, so the window opens with the
        # whole tree under the line rather than with an empty space that only
        # fills once a letter has been guessed at
        self._resuggest()
        self._redraw()

    # ------------------------------------------------------------------
    # Typing
    # ------------------------------------------------------------------

    async def handle_key(self, event: events.Key) -> bool:
        # Every key belongs to the line, including the ones the app binds
        # elsewhere: this is a text field, and `q` is a letter in it
        event.stop()

        key = self.resolve_key(event)

        # Escape is the way out of the window rather than a way to put the
        # list away, which is what it does in the one line entry: the list is
        # the whole of what is on screen here, and closing it would leave
        # nothing behind but the line it was answering
        if key == "escape":
            self.dismiss(None)
            return True

        if key == "enter":
            self._submit()
            return True

        # The keys that walk the list, and the tab that belongs to it even
        # when there is nothing to complete
        if self.handle_completion_key(key):
            return True

        self._input.keypress(key)

        # A warning is about the name as it was; the moment it is typed into
        # again it is about nothing
        self._warning = ""
        self._resuggest()
        self._redraw()

        return True

    # ------------------------------------------------------------------
    # Completing the project
    # ------------------------------------------------------------------

    def _completion_token(self) -> Optional[Token]:
        """
        The whole line, which is the only thing on it

        There is no marker to find and no cursor to consult: a line with
        nothing in it is a name nothing has been typed into yet, and every
        project answers to it.
        """

        return Token(0, len(self._input.value), self._input.value.strip())

    def _written(self, path: str, trailing: str) -> str:
        """
        A completed path, written in plainly

        Nothing quotes it, unlike the one line entry: there is nothing else on
        the line for a name with a space in it to run into.
        """

        return path + trailing

    def _completed(self) -> None:
        self._warning = ""
        self._redraw()

    # ------------------------------------------------------------------
    # Drawing
    # ------------------------------------------------------------------

    def _redraw(self) -> None:
        self.panel.update(Group(self._line(), self._preview(), *self._suggestions()))

    def _line(self) -> Text:
        # The buffer draws itself rather than being handed over as a string,
        # so that a selection made in it is highlighted here too
        buffer = self._input.render_editing(self.theme)
        buffer.style = Style(color=self.theme.foreground3)

        return Text(PROMPT, style=Style(color=self.theme.primary, bold=True)) + buffer

    def _preview(self) -> Text:
        """
        What is being moved and where to, or what stopped the last attempt

        The task is named throughout: the window can be opened from a pane
        that gathers work from all over the tree, and which of those rows the
        cursor was on is exactly what a window covering them cannot be asked.
        """

        if self._warning:
            return Text(self._warning, style=Style(color=self.theme.red, bold=True))

        faded = blend(self.theme.foreground1, self.theme.background2, IMPLIED_FADE)

        line = Text(self.todo.description, style=Style(color=faded))
        line.append(f"  {ARROW}  ", style=Style(color=faded))
        line.append_text(self._target_chip())

        return line

    def _target_chip(self) -> Text:
        """
        Where the task is going, said before it goes there

        The project it is in already while nothing has been typed, so the line
        opens by saying where the task stands rather than by leaving the answer
        blank; a name that answers to no project is drawn in red as it is
        typed, rather than being turned down after enter.
        """

        typed = self._input.value.strip()

        if not typed:
            return Text(
                f"{PROJECT_ICON} {self._where_it_is()}",
                style=Style(
                    color=blend(
                        self.theme.foreground1, self.theme.background2, IMPLIED_FADE
                    )
                ),
            )

        found = find_projects(typed)
        settled = len(found) == 1

        name = project_path(found[0]) if settled else project_display(typed)
        color = self.theme.primary if settled else self.theme.red

        return Text(f"{PROJECT_ICON} {name}", style=Style(color=color))

    def _where_it_is(self) -> str:
        """The project the task is filed under now, however deep inside it"""

        project = owning_project(self.todo)

        return project_path(project) if project else NOWHERE

    # ------------------------------------------------------------------
    # Moving
    # ------------------------------------------------------------------

    def _submit(self) -> None:
        """
        Files the task under the project the line names, or says why it cannot

        The line is left exactly as it was typed when it is turned down, rather
        than being cleared the way an unreadable task line is: what is wrong
        here is a name, and correcting a name is quicker than typing another.
        """

        typed = self._input.value.strip()

        if not typed:
            self._reject("Say which project to move it to")
            return

        found = find_projects(typed)

        if not found:
            self._reject(f"No project {project_display(typed)}")
            return

        if len(found) > 1:
            self._reject(
                f"More than one {project_display(typed)} — "
                f"try parent{PATH_SEPARATOR}{typed}"
            )
            return

        project = found[0]

        # Already filed straight under it, so there is nothing to do and
        # nothing to announce as having been done. Said rather than carried
        # out: a move that changes nothing still shuffles the task down to the
        # bottom of its own project. A step of another task is not "already
        # there" — moving it into the project is what takes it out of the task.
        if self.todo.parent_project == project:
            self._reject(f"Already in {project_path(project)}")
            return

        self.todo.move_to(project)
        self.dismiss(Moved(self.todo, project))

    def _reject(self, warning: str) -> None:
        self._warning = warning
        self._redraw()
