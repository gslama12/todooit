from functools import partial
from typing import TYPE_CHECKING, Any, List, Optional, Set, Tuple, Union

from rich.console import RenderableType
from rich.markup import escape
from rich.styled import Styled
from textual import on
from textual.color import Color
from textual.strip import Strip
from textual.style import Style
from textual.widgets.option_list import Option

from todooit.api import (
    Todo,
    Project,
    TodoGroup,
    TodoRow,
    freeze_sort_order,
    move_todo_to_bin,
    restore_todo,
    sort_todos,
)
from todooit.api.fixed_projects import PATH_SEPARATOR, owning_project
from todooit.ui.api.events import (
    BarNotification,
    RevealTodo,
    SpawnMove,
    SpawnNote,
    TodoChanged,
    TodoRemoved,
)
from todooit.ui.api.events.events import TodoSelected
from todooit.utils import blend, copy_text
from .model_tree import GroupHeading, ModelTree
from ._decorators import refresh_tree, require_highlighted_node
from ._render_dict import TodoRenderDict

if TYPE_CHECKING:  # pragma: no cover
    from ...api.api_components.formatters.model_formatters import (
        TodoFormatter,
    )

Model = Union[Todo, Project]

# How far a group heading fades towards the background — dimmer than the
# column titles, brighter than its own hairline, so it's found without being read
HEADING_FADE = 0.25


class TodosTree(ModelTree[Model, TodoRenderDict]):
    BORDER_TITLE = "TASKS"
    NODE_NOUN = "task"
    show_header = True
    CHILDREN_ATTR = "todos"

    # Alternating row shading strength, subtle enough to stay below the
    # cursor highlight. Only todos rows band — they have columns trailing off
    # to the right that need tying back to the description; projects don't.
    ROW_SHADE = 0.4

    # Whether a row is followed by its own children. True for whole-task
    # panes; a pane that gathers loose todos (parents off-screen) draws a flat list.
    show_children = True

    def __init__(self, model: Model) -> None:
        super().__init__(model, TodoRenderDict(self))

        # Indices where shading falls, computed block by block while building rows
        self._shaded_rows: Set[int] = set()

    @property
    def row_shade(self) -> Color:
        """The background the shaded half of the rows sits on"""

        theme = self.api.vars.theme
        return Color.parse(blend(theme.background1, theme.background2, self.ROW_SHADE))

    @property
    def _body_offset(self) -> int:
        """Index of the first row that is a todo rather than the column header"""

        if self._options and self._options[0].id == self.HEADER_ID:
            return 1

        return 0

    def _is_shaded(self, index: int) -> bool:
        """Whether the option at `index` is a banded row (precomputed, so headings never count and blocks restart unshaded)."""

        if not self.api.vars.row_shading:
            return False

        return (index - self._body_offset) in self._shaded_rows

    def _get_option_render(self, option: Option, style: Style) -> List[Strip]:
        """Bands rows, skipping the highlighted one (cursor owns its background) and any still flashing."""

        index = self._option_to_index.get(option)
        flashing = (option.id or "") in self._flashing

        if (
            not flashing
            and index is not None
            and index != self.highlighted
            and self._is_shaded(index)
        ):
            style += Style(background=self.row_shade)

        return super()._get_option_render(option, style)

    # Whether this pane draws binned todos or non-binned ones — a todo is in
    # exactly one bucket, so panes never show both
    shows_binned = False

    def visible_children(self, model: Model) -> List[Todo]:
        """
        Children this pane has a row for. A top-level completed/binned todo has moved
        to Completed/the Bin respectively; a completed *step* stays put under its
        still-pending parent.
        """

        if isinstance(model, Todo):
            todos = list(model.todos)
        else:
            todos = [todo for todo in model.todos if todo.pending]

        todos = [todo for todo in todos if todo.is_binned == self.shows_binned]

        return sort_todos(todos, self.sort_mode)

    @property
    def sort_mode(self) -> Optional[str]:
        """The order this pane reads its rows in, or None to leave them filed. Steps sort the same way as tasks."""

        return self.api.vars.todo_sort

    def sort_by(self, mode: str) -> bool:
        """
        Sets the order for every todos pane (not just this one — it's a global setting
        applied per pane), keeping the cursor on the same row. Returns False if this
        pane doesn't support sorting (its order is fixed).
        """

        self.api.vars.todo_sort = mode

        for tree in self.app.screen.query(TodosTree):
            tree._refresh_and_restore_highlight()

        return True

    def _drop_sort(self) -> None:
        """
        Before a manual reorder: bakes the current sorted order into the filing and
        clears the sort mode. Otherwise a shifted row would snap straight back to
        where the active sort puts it.
        """

        mode = self.sort_mode

        if mode is None:
            return

        freeze_sort_order(mode)
        self.api.vars.todo_sort = None

        # Global setting: every pane must re-read it now that it's cleared
        for tree in self.app.screen.query(TodosTree):
            if tree is not self:
                tree._refresh_and_restore_highlight()

        self.post_message(
            BarNotification(
                "Order is yours now — [b]SP[/b]/[b]SD[/b]/[b]SS[/b] sorts again",
                "info",
            )
        )

    def shift_up(self) -> None:
        self._drop_sort()
        super().shift_up()

    def shift_down(self) -> None:
        self._drop_sort()
        super().shift_down()

    def _heading_id(self, index: int) -> str:
        return f"todooit-todo-group-{index}"

    def _make_heading(self, label: str, space_above: bool) -> GroupHeading:
        theme = self.api.vars.theme

        return GroupHeading(
            label=label,
            label_style=blend(theme.foreground1, theme.background1, HEADING_FADE),
            rule_style=theme.background3,
            space_above=space_above,
        )

    @property
    def todo_groups(self) -> List[TodoGroup]:
        """
        The blocks of rows the pane draws: this project's own todos first (unlabelled),
        then a labelled block per nested sub-project (however deep), so work isn't
        hidden just because it lives one level down. Empty blocks are dropped.
        """

        groups = [TodoGroup(todos=self.visible_children(self.model))]

        if isinstance(self.model, Project):
            groups.extend(self._sub_project_groups(self.model))

        return [group for group in groups if group.todos]

    def _sub_project_groups(self, project: Project) -> List[TodoGroup]:
        """
        A block per nested sub-project, in projects-pane order, labelled by its
        full path down from here (not just its own name) to disambiguate
        same-named sub-projects at different depths.
        """

        groups: List[TodoGroup] = []

        def walk(parent: Project, prefix: str) -> None:
            for child in parent.projects:
                label = f"{prefix}{child.description}"
                groups.append(
                    TodoGroup(todos=self.visible_children(child), label=label)
                )
                walk(child, f"{label}{PATH_SEPARATOR}")

        walk(project, "")
        return groups

    def _body_options(self) -> List[Option]:
        """Every block of the pane, each under its own heading."""

        options: List[Option] = []
        self._shaded_rows = set()

        for index, group in enumerate(self.todo_groups):
            if group.label:
                options.append(
                    self.static_row(
                        self._heading_id(index),
                        partial(self._make_heading, group.label, bool(index)),
                    )
                )

            # Counts real rows only, so context/heading rows don't disturb the banding
            row = 0

            for todo, is_context in self._group_rows(group.rows):
                if is_context:
                    options.append(
                        self.static_row(
                            self._context_id(index, todo),
                            partial(self._make_context, todo.uuid),
                        )
                    )
                    continue

                if row % 2:
                    self._shaded_rows.add(len(options))

                row += 1
                options.append(Option("", id=self._renderers[todo.uuid].id))

        return options

    def _context_id(self, group: int, todo: Todo) -> str:
        """
        Id for a context row, keyed by its position rather than the todo — the same
        task can be context for more than one block (e.g. steps on different days).
        """

        return f"todooit-todo-context-{group}-{todo.id}"

    def _make_context(self, uuid: str) -> RenderableType:
        """A dimmed, disabled rendering of a task shown only as context for its own steps below."""

        return Styled(self._renderers[uuid].prompt, "dim")

    def _group_rows(self, rows: List[TodoRow]) -> List[Tuple[Todo, bool]]:
        """
        The rows a block draws in order, each flagged as context-only or not. A work
        row is followed by its expanded children; a context row only by the specific
        descendants the block picked, not its full subtree.
        """

        drawn: List[Tuple[Todo, bool]] = []

        for row in rows:
            drawn.append((row.todo, row.is_context))

            if row.is_context:
                drawn.extend(self._group_rows(row.under))
            else:
                drawn.extend((todo, False) for todo in self._steps_of(row.todo))

        return drawn

    def _steps_of(self, todo: Todo) -> List[Todo]:
        """The todos drawn under a row, as far as it's expanded."""

        if not self.draws_rows_under(todo):
            return []

        rows: List[Todo] = []

        for child in self.visible_children(todo):
            rows.append(child)
            rows.extend(self._steps_of(child))

        return rows

    def draws_rows_under(self, model: Any) -> bool:
        """A pane that never draws children has nothing under any row."""

        return self.show_children and super().draws_rows_under(model)

    def _get_parent(self, id: str) -> Optional[Todo]:
        return Todo.from_id(id).parent_todo

    def is_node_expaned(self, _id: str) -> bool:
        return super().is_node_expaned(_id) or self.api.vars.always_expand_todos

    @property
    def formatter(self) -> "TodoFormatter":
        return self.api.formatter.todos

    @property
    def render_layout(self):
        return self.api.layouts.todo_layout

    def _add_first_item(self) -> Todo:
        return self.model.add_todo()

    def _create_child_node(self) -> Todo:
        return self.current_model.add_todo()

    def _delete_current_model(self) -> None:
        assert isinstance(self.current_model, Todo)
        self.post_message(TodoRemoved(self.current_model))

        return super()._delete_current_model()

    def _bin_node(self) -> bool:
        """Bins the highlighted task with everything under it. Reversible, so no confirmation needed."""

        todo = self.current_model
        assert isinstance(todo, Todo)

        if todo.is_binned:
            self._already_binned()
            return False

        move_todo_to_bin(todo)
        self.post_message(TodoChanged(todo))
        return True

    def _binned_message(self, subject: str) -> str:
        """The cursor doesn't follow into the Bin, so tell the user the two keys to get there and restore."""

        return f"Binned {subject} — [b]gb[/b] then [b]u[/b] puts it back"

    def _already_binned(self) -> None:
        self.post_message(
            BarNotification(
                "Already in the Bin — [b]yy[/b] deletes it for good", "warning"
            )
        )

    def _restore_node(self) -> None:
        """Takes the highlighted task back out of the Bin."""

        todo = self.current_model
        assert isinstance(todo, Todo)

        if not todo.is_binned:
            self.post_message(
                BarNotification("Only tasks in the Bin can be restored", "warning")
            )
            return

        revived = restore_todo(todo)
        self.post_message(TodoChanged(todo))
        self.announce_revived(revived)

        # Row is gone from the Bin pane, so go to wherever it landed
        self.post_message(RevealTodo(todo))

    def announce_revived(self, projects: List[Project]) -> None:
        """
        Flashes and reports any projects that had to be rebuilt to give a restored
        task (from the Bin or completion log) somewhere to land.
        """

        if not projects:
            return

        tree = self.api.vars.projects_tree

        for project in projects:
            parent = project.parent_project

            # Ensure it's reachable — its own parent may also have just been rebuilt, and closed
            if parent is not None and not parent.is_root:
                tree.expanded_nodes[parent.uuid] = True

        tree.force_refresh()

        for project in projects:
            tree.flash_row(project.uuid)

        # Named after the rebuilt project, not the task — the task itself is
        # already visible with the cursor on it
        home = escape(projects[-1].description)
        self.post_message(
            BarNotification(f"Rebuilt [b]{home}[/b] to put it back", "info")
        )

    def _row_above(self, todo: Todo) -> Optional[Todo]:
        """The task drawn directly above this one, read off the pane's own display order, not the filing order."""

        return self.row_beside(todo, -1)

    @require_highlighted_node
    def indent_node(self) -> None:
        """Makes the highlighted task a step of the task above it, expanding that parent so the row stays visible."""

        todo = self.current_model
        assert isinstance(todo, Todo)

        parent = self._row_above(todo)

        if parent is None:
            self.post_message(
                BarNotification("Nothing above this to make it a step of", "warning")
            )
            return

        todo.indent(parent)

        # Expanding refreshes the pane, placing the row where it now belongs
        self._expand_node(parent.uuid)
        self.post_message(TodoChanged(todo))

    @require_highlighted_node
    @refresh_tree
    def unindent_node(self) -> None:
        """Takes the highlighted task out of the task it's a step of."""

        todo = self.current_model
        assert isinstance(todo, Todo)

        if todo.unindent() is None:
            self.post_message(
                BarNotification("This task is not a step of anything", "warning")
            )
            return

        self.post_message(TodoChanged(todo))

    def toggle_complete(self):
        todo = self.current_model
        assert isinstance(todo, Todo)

        was_scheduled_for = todo.scheduled

        todo.toggle_complete()
        self.refresh_options()

        # A recurring todo stays pending with a new date; flash it since the
        # row doesn't otherwise move to show something changed
        if todo.scheduled != was_scheduled_for:
            self.flash_row(todo.uuid)

    def set_priority(self, priority: int):
        assert isinstance(self.current_model, Todo)

        self.current_model.set_priority(priority)
        self.update_current_prompt()

    def toggle_agent(self):
        assert isinstance(self.current_model, Todo)

        self.current_model.toggle_agent()
        self.update_current_prompt()

    def show_note(self):
        assert isinstance(self.current_model, Todo)

        # Posted rather than pushed: the screen package imports the trees,
        # so calling it directly would create a circular import
        self.post_message(SpawnNote(self.current_model))

    @require_highlighted_node
    def move_node(self):
        """Opens the move window to pick a new project for the highlighted task; the move itself is its job, not this pane's."""

        assert isinstance(self.current_model, Todo)

        self.post_message(SpawnMove(self.current_model))

    @require_highlighted_node
    def goto_item(self):
        """
        Jumps to the highlighted task's real home project (opened, ancestors unfolded,
        row flashed) — relevant for fixed/gathered panes where the row lives elsewhere.
        No-ops with a message if already at home.
        """

        todo = self.current_model
        assert isinstance(todo, Todo)

        home = owning_project(todo)

        if home is not None and home.uuid == self.model.uuid:
            self.post_message(
                BarNotification("This is the project it lives in", "info")
            )
            return

        self.post_message(RevealTodo(todo))

    @require_highlighted_node
    def copy_note_to_clipboard(self):
        assert isinstance(self.current_model, Todo)

        note = self.current_model.note

        # Nothing changes on screen either way, so both outcomes need a bar message
        if not note.strip():
            self.post_message(BarNotification("This task has no note", "warning"))
            return

        copy_text(self.app, note)
        self.post_message(BarNotification("Note copied to clipboard", "info"))

    @on(ModelTree.OptionHighlighted)
    def todo_highlighted(self, event: ModelTree.OptionHighlighted):
        assert event.option_id

        event.stop()

        if self.is_static_row(event.option_id):
            return

        self.post_message(TodoSelected(Todo.from_id(event.option_id)))
