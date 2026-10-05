"""
The move window: type the project a task should be filed under

The whole line is the project name, completed via `.project_completion`
(shared with quick add).
"""

from typing import NamedTuple, Optional

from rich.console import Group
from rich.style import Style
from rich.text import Text

from todooit.api import Project, Todo
from todooit.api.fixed_projects import project_path
from todooit.api.placement import project_of
from todooit.utils.project_complete import Token

from .panel import HINT_GAP, PROJECT_ICON, PanelScreen
from .project_completion import ProjectCompletion, find_projects, project_display

PANEL_TITLE = "Move task"

# Between where the task is now and where it is going
ARROW = "→"

# Stands in for a missing project (a task whose project was deleted, in the Bin)
NOWHERE = "nowhere"

HINT = HINT_GAP.join(
    (
        "tab complete",
        "↑↓ pick",
        "esc cancel",
        "enter move",
    )
)


class Moved(NamedTuple):
    """What the window hands back once the task has been moved"""

    todo: Todo
    project: Project


class MoveScreen(ProjectCompletion, PanelScreen):
    PANEL_TITLE = PANEL_TITLE
    HINT = HINT

    def __init__(self, todo: Todo) -> None:
        super().__init__()

        # Held rather than looked up: the panes behind the window can't be asked
        self.todo = todo

        self._init_completion()

    def _opened(self) -> None:
        self.load_projects()

        # Open with the whole tree listed rather than an empty space
        self._resuggest()

    # ------------------------------------------------------------------
    # Typing
    # ------------------------------------------------------------------

    def line_key(self, key: str) -> None:
        # Escape closes the window: the list is all there is on screen
        if key == "escape":
            self.dismiss(None)
            return

        if key == "enter":
            self._submit()
            return

        if self.handle_completion_key(key):
            return

        self._input.keypress(key)

        self._warning = ""
        self._resuggest()
        self._redraw()

    # ------------------------------------------------------------------
    # Completing the project
    # ------------------------------------------------------------------

    def _completion_token(self) -> Optional[Token]:
        """The whole line is the name; an empty one matches every project"""

        return Token(0, len(self._input.value), self._input.value.strip())

    def _written(self, path: str, trailing: str) -> str:
        # Never quoted: nothing else is on the line for a space to run into
        return path + trailing

    def _completed(self) -> None:
        self._warning = ""
        self._redraw()

    # ------------------------------------------------------------------
    # Drawing
    # ------------------------------------------------------------------

    def _redraw(self) -> None:
        self.panel.update(Group(self._line(), self._preview(), *self._suggestions()))

    def _preview(self) -> Text:
        """`task → project`, or the warning from the last attempt"""

        if self._warning:
            return self._warning_text()

        faded = Style(color=self._faded_color())

        line = Text(self.todo.description, style=faded)
        line.append(f"  {ARROW}  ", style=faded)
        line.append_text(self._target_chip())

        return line

    def _target_chip(self) -> Text:
        """
        Where the task is going: its current project while nothing is typed,
        red while the name matches no project (or several, unpicked)
        """

        typed = self._input.value.strip()

        if not typed:
            return self._faded(f"{PROJECT_ICON} {self._where_it_is()}")

        found = find_projects(typed)
        settled = self.picked_among(found)

        if settled is None and len(found) == 1:
            settled = found[0]

        settled_on = settled is not None

        name = project_path(settled) if settled_on else project_display(typed)
        color = self.theme.primary if settled_on else self.theme.red

        return Text(f"{PROJECT_ICON} {name}", style=Style(color=color))

    def _where_it_is(self) -> str:
        project = project_of(self.todo)

        return project_path(project) if project else NOWHERE

    # ------------------------------------------------------------------
    # Moving
    # ------------------------------------------------------------------

    def _submit(self) -> None:
        """
        Moves the task, or says why not. The line is kept on rejection:
        fixing a name is quicker than retyping it.
        """

        typed = self._input.value.strip()

        if not typed:
            self._reject("Say which project to move it to")
            return

        found = find_projects(typed)

        if not found:
            self._reject(f"No project {project_display(typed)}")
            return

        # A pick from the list settles an ambiguous name (and is the only way
        # to pick a same-named top-level project, which has no parent to name)
        project = self.picked_among(found)

        if project is None:
            if len(found) > 1:
                self._reject(
                    f"More than one {project_display(typed)} — "
                    "↑↓ to pick which"
                )
                return

            project = found[0]

        # A no-op move would still shuffle the task to the bottom. A subtask of
        # another task is not "already there": moving lifts it out of its parent.
        if self.todo.parent_project == project:
            self._reject(f"Already in {project_path(project)}")
            return

        self.todo.move_to(project)
        self.dismiss(Moved(self.todo, project))
