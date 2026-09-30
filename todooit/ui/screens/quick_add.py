"""
Quick add: a whole task typed in one line, over the app

The line is parsed by `todooit.utils.quick_add`; this module draws the panel,
previews what the line was read as, and writes the task. A half typed
`#project` is completed via `.project_completion` (shared with move).
"""

from typing import List, NamedTuple, Optional

from rich.console import Group
from rich.style import Style
from rich.text import Text

from todooit.api import Project, Todo, lifecycle
from todooit.utils import day_label
from todooit.utils.project_complete import Token, find_token
from todooit.utils.quick_add import (
    DUE_MARKER,
    PATH_SEPARATOR,
    PROJECT_MARKER,
    SCALES,
    QuickAddError,
    QuickAddSpec,
    parse_quick_add,
    split_path,
)

from .panel import DATE_ICON, HINT_GAP, PROJECT_ICON, PanelScreen
from .project_completion import (
    ProjectCompletion,
    build_project,
    find_projects,
    project_display,
)

PANEL_TITLE = "Add task"

# Between the chips of the preview; narrow so six fields fit on one row
CHIP_GAP = "  "

# Asked when the line names a project that doesn't exist
CREATE_PROMPT = "No project {} — create it? [y/N]"

# Scales are read off `SCALES` so the legend can't go stale. `p0` is left
# out: it clears a priority, and a new task has none to clear.
SCALE_HINTS = tuple(
    f"{letter}1-{letter}{highest}" for letter, (_, highest) in SCALES.items()
)
HINT = HINT_GAP.join(
    (
        f"{PROJECT_MARKER}project",
        *SCALE_HINTS,
        "date",
        f"{DUE_MARKER}date",
        "   esc cancel",
        "enter add",
    )
)

# Shown instead of the legend while the create question stands
CREATE_HINT = "y  create it and add the task      any other key  back to the line"

# Shown instead of the legend while the project list is up
SUGGEST_HINT = HINT_GAP.join(
    (
        "tab complete",
        "↑↓ pick",
        "esc close list",
    )
)


class QuickAdded(NamedTuple):
    """What the overlay hands back when a task was added"""

    todo: Todo
    # Whether a project was built for it, which the projects pane must learn
    project_created: bool


class QuickAddScreen(ProjectCompletion, PanelScreen):
    PANEL_TITLE = PANEL_TITLE
    HINT = HINT

    # `#project` is one field of a sentence, so a finished one gets a space
    LEAF_TRAILING = " "

    def __init__(self, default_project: Optional[Project] = None) -> None:
        super().__init__()

        # Where a task goes when the line names no project. None when the
        # panes were on a fixed project; the line must then name one.
        self.default_project = default_project

        # A line naming a missing project, held while "create it?" is asked
        self._pending: Optional[QuickAddSpec] = None

        self._init_completion()

    def _opened(self) -> None:
        self.load_projects()

    @property
    def suggesting(self) -> bool:
        # The create question owns the keyboard, tab and arrows included
        return super().suggesting and self._pending is None

    # ------------------------------------------------------------------
    # Typing
    # ------------------------------------------------------------------

    def line_key(self, key: str) -> None:
        if self._pending is not None:
            self._answer_create(key)
            return

        # With the list up, escape closes the list rather than the window
        if self.suggesting and key == "escape":
            self.hide_suggestions()
            return

        if self.handle_completion_key(key):
            return

        if key == "escape":
            self.dismiss(None)
            return

        if key == "enter":
            self._submit()
            return

        self._input.keypress(key)

        self._warning = ""
        self._hidden = False
        self._resuggest()
        self._redraw()

    # ------------------------------------------------------------------
    # Completing the project
    # ------------------------------------------------------------------

    def _completion_token(self) -> Optional[Token]:
        """The `#project` the cursor stands in, if any"""

        if self._pending is not None:
            return None

        return find_token(self._input.value, self._input.cursor_position)

    def _completed(self) -> None:
        self._warning = ""
        self._redraw()

    # ------------------------------------------------------------------
    # Drawing
    # ------------------------------------------------------------------

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

    def _preview(self) -> Text:
        """
        The fields parsed so far, or the pending question, or the warning.
        An unparseable half-typed line just shows nothing until enter.
        """

        if self._pending is not None:
            return Text(
                CREATE_PROMPT.format(project_display(self._pending.project)),
                style=Style(color=self.theme.yellow, bold=True),
            )

        if self._warning:
            return self._warning_text()

        try:
            spec = parse_quick_add(self._input.value)
        except QuickAddError:
            return Text()

        return Text(CHIP_GAP).join(self._chips(spec))

    def _chips(self, spec: QuickAddSpec) -> List[Text]:
        theme = self.theme
        chips = [self._project_chip(spec)]

        if spec.priority:
            chips.append(
                Text(
                    f"p{spec.priority}",
                    style=Style(color=theme.foreground2, bold=True),
                )
            )

        # Scheduled then due, the order the row draws them; due is labelled
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
        The target project: red if named and not found, faded if assumed
        from the pane, a red placeholder if there is nothing to assume
        """

        theme = self.theme

        if not spec.project:
            if self.default_project is None:
                return Text(
                    f"{PROJECT_ICON} {PROJECT_MARKER}project",
                    style=Style(color=theme.red, dim=True),
                )

            return self._faded(f"{PROJECT_ICON} {self.default_project.description}")

        found = find_projects(spec.project)
        settled = self.picked_among(found)

        if settled is None and len(found) == 1:
            settled = found[0]

        color = theme.primary if settled is not None else theme.red
        name = settled.description if settled is not None else spec.project

        return Text(f"{PROJECT_ICON} {name}", style=Style(color=color))

    # ------------------------------------------------------------------
    # Adding
    # ------------------------------------------------------------------

    def _submit(self) -> None:
        """Writes the task, or warns and clears the line"""

        try:
            spec = parse_quick_add(self._input.value)
            project = self._target(spec)
        except QuickAddError as error:
            self._reject(str(error))
            return

        # An unknown project is a question, not an error
        if project is None:
            self._pending = spec
            self._redraw()
            return

        self.dismiss(QuickAdded(self._create(spec, project), False))

    def _answer_create(self, key: str) -> None:
        """`y` builds the project and adds the task; anything else restores the line"""

        spec, self._pending = self._pending, None
        assert spec is not None

        if key.lower() != "y":
            self._redraw()
            return

        project = build_project(split_path(spec.project))
        self.dismiss(QuickAdded(self._create(spec, project), True))

    def _target(self, spec: QuickAddSpec) -> Optional[Project]:
        """The project named or assumed; None if the named one doesn't exist"""

        if not spec.project:
            if self.default_project is None:
                raise QuickAddError(
                    f"Say which project, with {PROJECT_MARKER}name"
                )

            return self.default_project

        found = find_projects(spec.project)

        # A pick from the list settles an ambiguous name
        picked = self.picked_among(found)

        if picked is not None:
            return picked

        if len(found) > 1:
            raise QuickAddError(
                f"More than one {spec.project} — "
                f"try {PROJECT_MARKER}parent{PATH_SEPARATOR}{spec.project}"
            )

        return found[0] if found else None

    @staticmethod
    def _create(spec: QuickAddSpec, project: Project) -> Todo:
        todo = project.add_todo()

        todo.description = spec.description
        todo.priority = spec.priority

        # Placed first, then dated through the lifecycle: the same rules
        # as for a todo created in the tree and then edited
        lifecycle.schedule(todo, spec.scheduled)
        lifecycle.set_due(todo, spec.due)

        return todo

    def _reject(self, warning: str) -> None:
        # Unlike move, the line is cleared: retyping one line beats hunting
        # for the bad word in it
        self._input.clear_input()
        super()._reject(warning)
