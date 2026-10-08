from functools import partial
from typing import TYPE_CHECKING, List, Optional, Union

from rich.console import RenderableType
from rich.markup import escape
from rich.styled import Styled
from textual import on
from textual.widgets.option_list import Option

from todooit.api import (
    Project,
    Todo,
    TodoGroup,
    TodoSortModeType,
    freeze_sort_order,
    move_todo_to_bin,
    restore_todo,
)
from todooit.api.placement import home_of
from todooit.ui.api.events import (
    BarNotification,
    RevealTodo,
    SpawnMove,
    SpawnNote,
)
from todooit.ui.api.events.events import TodoSelected
from todooit.ui.pane_layout import (
    PaneRow,
    drawn_children,
    project_groups,
    todo_rows,
)
from todooit.utils import blend, copy_text

from ._decorators import require_highlighted_node
from ._render_dict import TodoRenderDict
from .model_tree import GroupHeading, ModelTree

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

    # What I and U say when there is nowhere to move the task
    NOTHING_ABOVE = "Nothing above this to make it a step of"
    NOT_NESTED = "This task is not a step of anything"
    show_header = True
    CHILDREN_ATTR = "todos"

    def __init__(self, model: Model) -> None:
        super().__init__(model, TodoRenderDict(self))

    def visible_children(self, model: Model) -> List[Todo]:
        """Children this pane has a row for, in its order (see pane_layout)."""

        return drawn_children(model, self.sort_mode)

    @property
    def sort_mode(self) -> Optional[str]:
        """The order this pane reads its rows in, or None to leave them filed. Steps sort the same way as tasks."""

        return self.api.vars.todo_sort

    def sort_by(self, mode: TodoSortModeType) -> bool:
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

    def make_heading(self, row: PaneRow) -> GroupHeading:
        theme = self.api.vars.theme

        return GroupHeading(
            label=row.label,
            label_style=blend(theme.foreground1, theme.background1, HEADING_FADE),
            rule_style=theme.background3,
            space_above=bool(row.block),
        )

    def make_context(self, row: PaneRow) -> RenderableType:
        """A dimmed, disabled rendering of a task shown only as context for its own steps below."""

        return Styled(self.render_row(row), "dim")

    @property
    def todo_groups(self) -> List[TodoGroup]:
        """The blocks of rows the pane draws (see pane_layout.project_groups)."""

        return project_groups(self.model, self.sort_mode)

    def pane_rows(self) -> List[PaneRow]:
        return todo_rows(self.todo_groups, self.visible_children, self.is_node_expaned)

    def option_for(self, row: PaneRow) -> Option:
        """Headings and context rows are drawn but never land the cursor."""

        if row.is_heading:
            return self.static_row(row.id, partial(self.make_heading, row))

        if row.is_context:
            return self.static_row(row.id, partial(self.make_context, row))

        return super().option_for(row)

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

    def _bin_node(self) -> bool:
        """Bins the highlighted task with everything under it. Reversible, so no confirmation needed."""

        todo = self.current_model
        assert isinstance(todo, Todo)

        if todo.is_binned:
            self._already_binned()
            return False

        move_todo_to_bin(todo)
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

    def toggle_complete(self):
        todo = self.current_model
        assert isinstance(todo, Todo)

        outcome = todo.toggle_complete()
        self.refresh_options()

        # An advanced todo stays open with a new date; flash it since the
        # row doesn't otherwise move to show something changed
        if outcome.advanced:
            self.flash_row(todo.uuid)

        self.tell_outcome(outcome)
        self.announce_revived(outcome.revived)

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
        Jumps to the highlighted todo's home (opened, ancestors unfolded,
        row flashed) — relevant for fixed/gathered panes where the row lives elsewhere.
        No-ops with a message if already at home.
        """

        todo = self.current_model
        assert isinstance(todo, Todo)

        home = home_of(todo)

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

        # Imported here: the screens package imports the widgets
        from todooit.ui.screens.note.markdown import to_markdown

        copy_text(self.app, to_markdown(note))
        self.post_message(BarNotification("Note copied to clipboard", "info"))

    @on(ModelTree.OptionHighlighted)
    def todo_highlighted(self, event: ModelTree.OptionHighlighted):
        assert event.option_id

        event.stop()

        if self.is_static_row(event.option_id):
            return

        self.post_message(TodoSelected(Todo.from_id(event.option_id)))
