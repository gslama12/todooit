from datetime import datetime
from typing import Any, Dict, List, Optional, Set

from rich.style import Style
from rich.text import Text
from textual.widgets.option_list import Option

from todooit.api import FixedProject, Todo, TodoGroup, TodoRow
from todooit.api.fixed_projects import PATH_SEPARATOR, owning_project
from todooit.ui.api.events import BarNotification, StartFieldEdit
from todooit.ui.api.widgets import TodoWidget
from todooit.utils import blend
from .todos_tree import TodosTree

# The folder the projects pane draws its rows with, so a row that names its
# project here is recognisably pointing back at a row over there
OWNER_ICON = "󰉋"

# How far the project trailing a row is pulled towards the background. Further
# than anything else on the row: it is there to be found once a row has been
# read, never to be scanned down the pane.
OWNER_FADE = 0.55

# What leads a row that was planned for a day already gone by. A word rather
# than a symbol, and the word for what the row is here to have done to it: the
# pane it is sitting in is the one it gets rescheduled from
RESCHEDULE_MARK = "Reschedule: "

# How much of a row a trailing project name may take before it is cut short.
# It shares a column with the description, which is the one thing on the row
# that has to stay readable, so a long project name gives way to it. A fixed
# cap rather than a share of the pane: a row is drawn once, and a pane that
# has just been opened has not been given its width yet
OWNER_MAX_WIDTH = 16

ELLIPSIS = "…"


class FixedTodosTree(TodosTree):
    """
    The tasks of a fixed project, gathered from across the whole tree

    The rows are the same todos every other pane shows, in the same columns:
    what a fixed project adds is that they arrive from more than one project at
    once, in blocks under whatever heading it chose to gather them by. A
    project that groups by anything but the project itself has each row say
    where it came from, since its headings no longer do.
    """

    # A row of a fixed project is a whole task: whatever it was gathered for,
    # it is drawn with the steps filed under it beneath it, as far as it is
    # expanded, exactly the way the project it came from draws it
    show_children = True
    show_guides = True

    def __init__(self, model: FixedProject) -> None:
        super().__init__(model)

        # The rows that open a block, taken down as the pane is built. They
        # are where the guides stop and where the project names on the rows
        # start: what hangs off one of them came along with it, and belongs to
        # it rather than to the pane
        self._row_roots: Set[str] = set()

        # Of the rows a block picked out itself, which are the last of the
        # ones drawn beside them. A context row shows only the work the block
        # gathered, so the row that ends a family here is rarely the one that
        # ends it in the project it came from
        self._last_rows: Dict[str, bool] = {}

    @property
    def model(self) -> FixedProject:
        return self._model

    def _body_options(self) -> List[Option]:
        self._row_roots = set()
        self._last_rows = {}

        for group in self.todo_groups:
            self._row_roots.update(row.todo.uuid for row in group.rows)
            self._note_drawn(group.rows)

        return super()._body_options()

    def _note_drawn(self, rows: List[TodoRow]) -> None:
        """
        Takes down where each of a block's own rows falls among the ones beside it
        """

        for row in rows:
            if not row.is_context:
                continue

            for index, child in enumerate(row.under):
                self._last_rows[child.todo.uuid] = index == len(row.under) - 1

            self._note_drawn(row.under)

    def is_row_root(self, model: Any) -> bool:
        return model.uuid in self._row_roots or not model.nest_level

    def is_last_row(self, model: Any) -> bool:
        last = self._last_rows.get(model.uuid)

        return super().is_last_row(model) if last is None else last

    def _get_parent(self, id: str) -> Optional[Todo]:
        """
        The row a row hangs off, if this pane drew that one too

        A gathered row can be a step of a task that was not gathered: the task
        it belongs to is nowhere on screen, so there is nothing here to fold
        the row back into.
        """

        if self.is_row_root(Todo.from_id(id)):
            return None

        return super()._get_parent(id)

    @property
    def sort_mode(self) -> None:
        """
        A fixed project orders its own rows, and is not re-ordered over

        The order is half of what the project is: Today reads by priority
        because that is the question the day asks, and Completed by the date
        each row was ticked off. An order picked for a stored project has
        nothing to say about either.
        """

        return None

    @property
    def todo_groups(self) -> List[TodoGroup]:
        """
        The blocks of rows the pane draws

        Whatever the fixed project gathered, which is the whole of it unless
        the pane is holding rows of its own alongside them.
        """

        return self.model.todo_groups

    @property
    def render_layout(self) -> List:
        """
        The columns of the pane: the layout's, less the ones its headings
        already say, plus whatever it has of its own to put there instead

        A column of its own goes in right behind the description, where the
        dates it stands in for would have been, rather than out at the end of
        the row past the columns nobody hid.
        """

        hidden = set(self.model.hidden_columns)
        layout = [item for item in super().render_layout if item.value not in hidden]

        extras = [TodoWidget(name) for name in self.model.extra_columns]
        extras = [item for item in extras if item not in layout]

        if not extras:
            return layout

        after = 0
        for index, item in enumerate(layout):
            if item.value == "description":
                after = index + 1
                break

        return layout[:after] + extras + layout[after:]

    @property
    def editable_columns(self) -> List[str]:
        """
        A column left out of the pane is still a column of the todo behind it
        """

        return [item.value for item in super().render_layout]

    def column_value(self, attr: str, component: Any) -> Any:
        return self._as_shown(attr, super().column_value(attr, component))

    def _as_shown(self, attr: str, value: Any) -> Any:
        """
        A day-only column handed to the formatters as the day it falls on

        The pane is read a day at a time, so the hour is noise beside the
        headings. Rounding the value down is what leaves it out, rather than
        the pane having any say in how a date is written.
        """

        if attr in self.model.day_only_columns and isinstance(value, datetime):
            return value.replace(hour=0, minute=0, second=0, microsecond=0)

        return value

    def start_edit(self, property: str) -> bool:
        started = super().start_edit(property)

        # Nowhere in the row to draw the buffer, so the bar takes it. Making
        # room for the column instead would shift the whole pane sideways the
        # moment an edit started, and back again the moment it ended.
        if started and property in self.model.hidden_columns:
            self.post_message(StartFieldEdit(self, property))

        return started

    def row_mark(self, model) -> Text:
        """
        What is to be done with a row that slipped in from a day gone by

        Only in the panes that carry such work onto today, where the row sits
        among the day's own work with nothing on it to say it does not belong
        to the day. In front of the description rather than after it: it is
        not another thing known about the row, it is what the row is doing in
        a pane it was never planned into.

        Every row of a family says it, not just the gathered one: a step that
        was left behind was left behind whether or not the task above it was.
        """

        if not self.model.marks_overscheduled or not isinstance(model, Todo):
            return Text()

        if not model.is_overscheduled:
            return Text()

        theme = self.api.vars.theme

        # Assembled rather than styled as a whole, so that the red stays on
        # the mark instead of bleeding into the description behind it
        return Text.assemble((RESCHEDULE_MARK, Style(color=theme.red)))

    def row_note(self, model) -> Text:
        """
        The project a row was pulled out of, at the far end of its description

        Only for the fixed projects grouped by something other than the
        project: the ones with a block per project have said it already. What
        it shows is the project's own name rather than its whole path, which
        is what keeps it to the end of a line it is sharing.

        Only the gathered row says it, never the steps under it: they came out
        of the same project it did, and saying so on every row of a family
        would say it three times over.

        A todo that outlived its project has the name it was filed under
        instead, which is the name the project comes back under if the todo
        does.
        """

        if not self.model.show_owning_project or not isinstance(model, Todo):
            return Text()

        if not self.is_row_root(model):
            return Text()

        name = self._owner_name(model)

        if not name:  # pragma: no cover
            return Text()

        theme = self.api.vars.theme
        style = Style(color=blend(theme.foreground1, theme.background1, OWNER_FADE))

        return Text(f"  {OWNER_ICON} {self._fit(name)}", style=style)

    @staticmethod
    def _owner_name(todo: Todo) -> str:
        """
        What a row calls the project it belongs to, gone or not
        """

        project = owning_project(todo)

        if project is not None:
            return project.description

        # Only the last step of the path: the row has room for a name, and the
        # name is the part of the path that says which project this was
        return todo.origin_path.split(PATH_SEPARATOR)[-1].strip()

    @staticmethod
    def _fit(name: str) -> str:
        """
        A project name cut down to what it may take of the row it trails
        """

        if len(name) <= OWNER_MAX_WIDTH:
            return name

        return name[: OWNER_MAX_WIDTH - 1] + ELLIPSIS

    # ---------------------------------------------------------------
    # A fixed project owns none of the todos it shows: they can be worked on
    # here, but where they live and what order they come in is decided by the
    # project they really belong to
    # ---------------------------------------------------------------

    def _not_here(self, what: str) -> None:
        self.post_message(
            BarNotification(f"{what} in [b]{self.model.title}[/b]", "warning")
        )

    def _new_sibling(self) -> None:
        self._not_here("Tasks can't be added")
        return None

    def add_child_node(self):
        self._not_here("Tasks can't be added")

    def indent_node(self) -> None:
        self._not_here("Tasks can't be reordered")

    def unindent_node(self) -> None:
        self._not_here("Tasks can't be reordered")

    def shift_up(self) -> None:
        self._not_here("Tasks can't be reordered")

    def shift_down(self):
        self._not_here("Tasks can't be reordered")

    def start_sort(self):
        self._not_here("Tasks can't be sorted")

    def sort_by(self, mode: str) -> bool:
        """
        The order keys do nothing here, rather than quietly re-ordering
        elsewhere

        The order is the pane's, so taking it from a project that has no say
        in its own would leave the key looking like it had missed: nothing
        moves here, and what did move is a pane nobody is looking at.
        """

        self._not_here("Tasks can't be sorted")
        return False
