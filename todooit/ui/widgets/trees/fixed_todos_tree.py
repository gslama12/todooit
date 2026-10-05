from datetime import datetime
from typing import Any, Callable, Dict, List, Optional, Set, Tuple

from rich.style import Style
from rich.text import Text
from textual.widgets.option_list import Option

from todooit.api import FixedProject, Todo, TodoGroup, TodoRow
from todooit.api.fixed_projects import PATH_SEPARATOR
from todooit.api.placement import project_of
from todooit.ui.api.events import BarNotification, StartFieldEdit
from todooit.ui.api.widgets import TodoWidget
from todooit.utils import blend
from .todos_tree import TodosTree

# Same folder icon the projects pane uses, so a row visibly points back to its project
OWNER_ICON = "󰉋"

# How far the trailing project name is faded towards the background — more
# than anything else on the row, since it's meant to be looked up, not scanned
OWNER_FADE = 0.55

# Marks the day a row carried onto today was actually planned for (day.month
# only — old enough to need the year is old enough not to reschedule this way)
RESCHEDULE_FORMAT = "(%d.%m.) "


def reschedule_mark(day: datetime) -> str:
    """The day a slipped row was planned for, as shown on the row."""

    return day.strftime(RESCHEDULE_FORMAT)


# Max width of a trailing project name before it's cut short. Fixed rather
# than proportional, since a row is drawn before the pane has a known width;
# the description, which shares the line, has to stay readable.
OWNER_MAX_WIDTH = 16

ELLIPSIS = "…"


class FixedTodosTree(TodosTree):
    """
    Tasks gathered from across the whole tree into blocks under a heading.

    Same rows and columns as any todos pane, except rows can come from
    multiple projects; when grouped by anything but project, each row also
    says where it came from.
    """

    # A row that draws its own steps (the log, the bin) does so exactly as its
    # own project would; a day pane picks the steps each row draws instead
    show_children = True
    show_guides = True

    def __init__(self, model: FixedProject) -> None:
        super().__init__(model)

        # uuids of rows that open a block: where guides stop and owner names start
        self._row_roots: Set[str] = set()

        # A todo can be drawn in several blocks (as work in one, as context in
        # others), each time with other rows beside and under it, so what the
        # guides read is kept per (block, uuid) rather than per todo.

        # Is this row the last drawn beside its siblings in its block?
        self._last_rows: Dict[Tuple[int, str], bool] = {}

        # Did the block pick anything to draw under this row?
        self._rows_under: Dict[Tuple[int, str], bool] = {}

        # The rows drawn as context, and the one block each work row is in
        self._context_rows: Set[Tuple[int, str]] = set()
        self._work_block: Dict[str, int] = {}

        # The block of the row being drawn right now, while it is drawn
        self._drawing_block: Optional[int] = None

    @property
    def model(self) -> FixedProject:
        return self._model

    def _body_options(self) -> List[Option]:
        self._row_roots = set()
        self._last_rows = {}
        self._rows_under = {}
        self._context_rows = set()
        self._work_block = {}

        for index, group in enumerate(self.todo_groups):
            self._row_roots.update(row.todo.uuid for row in group.rows)
            self._note_drawn(index, group.rows)

        return super()._body_options()

    def _note_drawn(self, block: int, rows: List[TodoRow]) -> None:
        """Records where each row the block picked falls, for the guides."""

        for row in rows:
            if row.under is None:
                continue

            key = (block, row.todo.uuid)

            if row.is_context:
                self._context_rows.add(key)
            else:
                self._work_block[row.todo.uuid] = block

            self._rows_under[key] = bool(row.under)

            for index, child in enumerate(row.under):
                self._last_rows[(block, child.todo.uuid)] = index == len(row.under) - 1

            self._note_drawn(block, row.under)

    def _in_block(self, block: Optional[int], make: Callable[[], Any]) -> Any:
        """Draws a row with the guides of the block it is drawn in."""

        self._drawing_block = block

        try:
            return make()
        finally:
            self._drawing_block = None

    def _occurrence(self, model: Any) -> Tuple[Optional[int], str]:
        block = self._drawing_block

        if block is None:
            block = self._work_block.get(model.uuid)

        return block, model.uuid

    def prompt_for(self, _id: str) -> Any:
        block = self._work_block.get(_id)

        if block is None:
            return super().prompt_for(_id)

        return self._in_block(block, lambda: super(FixedTodosTree, self).prompt_for(_id))

    def _make_context(self, group: int, uuid: str) -> Any:
        return self._in_block(group, lambda: super(FixedTodosTree, self)._make_context(group, uuid))

    def is_row_root(self, model: Any) -> bool:
        return model.uuid in self._row_roots or not model.nest_level

    def is_last_row(self, model: Any) -> bool:
        last = self._last_rows.get(self._occurrence(model))

        return super().is_last_row(model) if last is None else last

    def draws_rows_under(self, model: Any) -> bool:
        key = self._occurrence(model)
        under = self._rows_under.get(key)

        if under is None:
            return super().draws_rows_under(model)

        return under and (key in self._context_rows or self.is_node_expaned(model.uuid))

    def _get_parent(self, id: str) -> Optional[Todo]:
        """The parent row, only if this pane also drew it — a gathered row's real parent may be off-screen."""

        if self.is_row_root(Todo.from_id(id)):
            return None

        return super()._get_parent(id)

    @property
    def sort_mode(self) -> None:
        """A fixed project orders its own rows (e.g. Today by priority, Completed by date) and ignores the global sort."""

        return None

    @property
    def todo_groups(self) -> List[TodoGroup]:
        """The blocks of rows the pane draws, as gathered by the fixed project."""

        return self.model.todo_groups

    @property
    def render_layout(self) -> List:
        """
        The layout's columns minus ones its headings already cover, plus its own extra
        columns inserted right after the description (not tacked on at the end).
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
        """A column hidden from display is still editable — it's still a real column of the todo."""

        return [item.value for item in super().render_layout]

    def column_value(self, attr: str, component: Any) -> Any:
        return self._as_shown(attr, super().column_value(attr, component))

    def _as_shown(self, attr: str, value: Any) -> Any:
        """Strips the time of day off day-only columns, since the pane groups by day."""

        if attr in self.model.day_only_columns and isinstance(value, datetime):
            return value.replace(hour=0, minute=0, second=0, microsecond=0)

        return value

    def start_edit(self, property: str) -> bool:
        started = super().start_edit(property)

        # No room in the row for a hidden column's edit buffer, so the bar
        # takes it instead of shifting the whole pane to make space
        if started and property in self.model.hidden_columns:
            self.post_message(StartFieldEdit(self, property))

        return started

    def row_mark(self, model) -> Text:
        """
        Marks a row carried onto today from an earlier day with the day it was planned for,
        before the description. Applies to every row of the family, not just the gathered one,
        since a left-behind step is left behind regardless of its parent task.
        """

        if not self.model.marks_overscheduled or not isinstance(model, Todo):
            return Text()

        if not model.is_overscheduled:
            return Text()

        theme = self.api.vars.theme

        mark = reschedule_mark(model.scheduled)

        # Assembled, not styled whole, so red stays on the mark, not the description
        return Text.assemble((mark, Style(color=theme.red)))

    def row_note(self, model) -> Text:
        """
        Shows the source project's name after a row's description, for fixed projects
        grouped by something other than project (those already say it via headings).
        Only on the gathered row, not its steps, to avoid repeating it. A todo whose
        project was dropped falls back to the project name from its stored path.
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
        """The name of the project a row belongs to, whether or not it still exists."""

        project = project_of(todo)

        if project is not None:
            return project.description

        # Last segment of the stored path: that's the project's name
        return todo.origin_path.split(PATH_SEPARATOR)[-1].strip()

    @staticmethod
    def _fit(name: str) -> str:
        """Truncates a trailing project name to `OWNER_MAX_WIDTH`."""

        if len(name) <= OWNER_MAX_WIDTH:
            return name

        return name[: OWNER_MAX_WIDTH - 1] + ELLIPSIS

    # ---------------------------------------------------------------
    # A fixed project owns none of the todos it shows: they can be worked on
    # here, but where they live and what order they come in is decided by the
    # project they really belong to
    # ---------------------------------------------------------------

    # Whether a row here can take a new step: yes for panes of pending work
    # (filed under the task's real project), no for logs of work that's left
    # the tree (nothing there to break down further)
    takes_new_steps = True

    def _not_here(self, what: str, instead: str = "") -> None:
        """Reports what this pane won't do and, if given, what to do instead. Names the project every time."""

        message = f"{what} in [b]{self.model.title}[/b]"

        if instead:
            message = f"{message} — {instead}"

        self.post_message(BarNotification(message, "warning"))

    def _new_sibling(self) -> None:
        """No sibling slot here — rows are gathered from the whole tree, so there's no single project to add one to."""

        instead = "[b]N[/b] adds a step to one" if self.takes_new_steps else ""

        self._not_here("Tasks can't be added", instead)
        return None

    def add_child_node(self):
        """Adds a step under the highlighted task, filed in that task's real project (not this pane)."""

        if not self.takes_new_steps:
            self._not_here("Steps can't be added")
            return

        return super().add_child_node()

    def indent_node(self) -> None:
        self._not_here("Tasks can't be reordered")

    def unindent_node(self) -> None:
        self._not_here("Tasks can't be reordered")

    def shift_up(self) -> None:
        self._not_here("Tasks can't be reordered")

    def shift_down(self):
        self._not_here("Tasks can't be reordered")

    def sort_by(self, mode: str) -> bool:
        """Sort keys do nothing here — the pane's order is fixed, not user-selectable — rather than silently sorting elsewhere."""

        self._not_here("Tasks can't be sorted")
        return False
