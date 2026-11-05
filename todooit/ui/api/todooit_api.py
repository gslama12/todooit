from contextlib import contextmanager
from traceback import format_exc
from typing import TYPE_CHECKING, Callable, Iterator, List, Optional, Union

from todooit.api import (
    BIN,
    COMPLETED,
    TODAY,
    UPCOMING,
    History,
    Project,
    Todo,
    TodoSortModeType,
    binned_tasks,
    completed_tasks,
    empty_bin,
    empty_completed,
)
from todooit.ui.api.events import BarNotification, NotificationType
from todooit.ui.api.plug import ConfigManager
from todooit.ui.widgets import ModelTree
from todooit.ui.widgets.trees import ProjectsTree, TodosTree
from todooit.utils import CssManager, first_link, link_label, open_url

from .api_components import (
    BarManager,
    Formatter,
    KeyManager,
    KeyMatchType,
    KeyScopeType,
    LayoutManager,
    MotionKeys,
    VarManager,
    VimManager,
)
from .events import (
    GotoFixedProject,
    HistoryStep,
    QuitApp,
    ShowConfirm,
    SpawnHelp,
    SpawnQuickAdd,
    SpawnSearch,
    TodooitEvent,
)

if TYPE_CHECKING:  # pragma: no cover
    from ..tui import Todooit


# Display labels for sort orders; "scheduled" alone reads oddly in a sentence.
SORT_LABELS = {
    "priority": "priority",
    "due": "due date",
    "scheduled": "scheduled date",
}


class TodooitAPI:
    def __init__(
        self,
        app: "Todooit",
    ) -> None:
        self.app = app

        # Set before any formatter store is built: a store checks this on
        # write to see if a batch is collecting. None = no batch.
        self._formatter_batch: Optional[List[Callable]] = None

        self.config_manager = ConfigManager(self, app.config)
        self.css = CssManager()
        self.keys = KeyManager(self.app.get_todooit_mode, self.key_scope)
        self.layouts = LayoutManager(self.app)
        self.formatter = Formatter(self)
        self.bar = BarManager(self)
        self.vars = VarManager(self)
        self.vim = VimManager()
        self.history = History()

        self.css.refresh_css()

    @contextmanager
    def batch_formatter_refresh(self) -> Iterator[None]:
        """
        Collects redraws requested by formatters and runs each once, instead
        of once per formatter. Re-entrant (an inner batch joins the outer
        one). Flush happens in `finally`, so a raising handler still closes
        the batch and redraws instead of leaving it stuck open.
        """

        if self._formatter_batch is not None:
            yield
            return

        self._formatter_batch = []

        try:
            yield
        finally:
            pending, self._formatter_batch = self._formatter_batch, None

            for trigger in pending:
                trigger()

    def no_op(self):
        """<NOP>"""

    def quit(self):
        """Quit todooit"""
        self.app.post_message(QuitApp())

    def notify(self, message: str, level: NotificationType = "info") -> None:
        self.app.bar_switcher.switch_to_notification(BarNotification(message, level))

    def key_scope(self) -> Optional[KeyScopeType]:
        """
        The pane a key is being pressed over, for pane-scoped bindings.
        Anything else focused (a bar, or nothing) has no scope, so only
        unscoped bindings apply.
        """

        focused = self.app.focused

        if isinstance(focused, TodosTree):
            return "todos"

        if isinstance(focused, ProjectsTree):
            return "projects"

        return None

    def motion_keys(self) -> MotionKeys:
        """
        The direction keys, read off the panes' own bindings so the overlays
        always steer with whatever the panes move with. A direction with no
        single-key binding falls back to its arrow key.
        """

        keys = self.keys

        return MotionKeys(
            left=keys.key_for(self.focus_projects) or "left",
            right=keys.key_for(self.focus_todos) or "right",
            up=keys.key_for(self.move_up) or "up",
            down=keys.key_for(self.move_down) or "down",
        )

    def handle_key(self, key: str) -> None:
        # While flash labels are up every key is a label (or the way out), so
        # none of them reaches the keybindings
        focused = self.app.focused
        if isinstance(focused, ModelTree) and focused.is_flashing:
            focused.handle_flash_key(key)
            return

        keymatch = self.keys.register_key(key)

        if keymatch.match_type == KeyMatchType.NoMatchFound:
            self.focused.handle_keypress(key)
            return

        if keymatch.match_type == KeyMatchType.MultipleMatchFound:
            return

        assert keymatch.function is not None
        try:
            keymatch.function.callback()
        except Exception as e:
            self.app.bar_switcher.switch_to_notification(
                BarNotification(str(e), "error", details=format_exc())
            )

    def trigger_event(self, event: TodooitEvent):
        self.config_manager.on_event(event)

    # -----------------------------------------

    @property
    def focused(self) -> ModelTree:
        focused = self.app.focused
        if isinstance(focused, ModelTree):
            return focused

        raise ValueError(f"Expected BaseTree, got {type(focused)}")

    def copy_description_to_clipboard(self):
        """Copy the description of the focused item to the clipboard"""

        self.focused.copy_description_to_clipboard()

    def copy_note_to_clipboard(self):
        """Copy the note of the highlighted todo to the clipboard"""

        if isinstance(self.focused, TodosTree):
            self.focused.copy_note_to_clipboard()

    def paste_as_sibling(self):
        """Add an item described by whatever is on the clipboard"""

        self.focused.paste_as_sibling()

    def focus_projects(self):
        """Move focus to the projects pane"""

        if self.app.bar_switcher.is_focused:
            return

        self.app.project_tree.focus()

    def focus_todos(self):
        """Move focus to the todos pane"""

        if self.app.bar_switcher.is_focused:
            return

        if todos_tree := self.vars.todos_tree:
            todos_tree.focus()

    def goto_fixed_project(self, key: str):
        """Open a fixed project and start on the first of its tasks"""

        if self.app.bar_switcher.is_focused:
            return

        # Posted at the screen, which owns both panes and can move between them.
        self.app.screen.post_message(GotoFixedProject(key))

    def goto_today(self):
        """Jump to Today and start on the first task scheduled for it"""

        self.goto_fixed_project(TODAY.key)

    def goto_upcoming(self):
        """Jump to Upcoming and start on the nearest day's first task"""

        self.goto_fixed_project(UPCOMING.key)

    def goto_completed(self):
        """Jump to Completed and start on the task finished last"""

        self.goto_fixed_project(COMPLETED.key)

    def goto_bin(self):
        """Jump to the Bin and start on the task thrown away last"""

        self.goto_fixed_project(BIN.key)

    def goto_item(self):
        """Jump to the highlighted task in the project it is filed under"""

        if isinstance(self.focused, TodosTree):
            self.focused.goto_item()

    def move_down(self):
        """Move the cursor down in the focused list"""

        self.focused.action_cursor_down()

    def move_up(self):
        """Move the cursor up in the focused list"""

        self.focused.action_cursor_up()

    def shift_up(self):
        """Shift the highlighted item up"""

        self.focused.shift_up()

    def shift_down(self):
        """Shift the highlighted item down"""

        self.focused.shift_down()

    def indent(self):
        """File the highlighted task or project under the one above it"""

        self.focused.indent_node()

    def unindent(self):
        """Take the highlighted task or project out of the one it is under"""

        self.focused.unindent_node()

    def move_todo(self):
        """File the highlighted task under another project"""

        if isinstance(self.focused, TodosTree):
            self.focused.move_node()

    def go_to_top(self):
        """Move the cursor to the top of the list"""
        self.focused.action_first()

    def go_to_bottom(self):
        """Move the cursor to the bottom of the list"""
        self.focused.action_last()

    def flash_jump(self):
        """Label the rows on screen and jump to the one whose label is typed"""

        self.focused.start_flash()

    def edit(self, property: str):
        """Start editing a property of the focused item"""
        self.focused.start_edit(property)

    def edit_description(self):
        """Start editing the description of the focused item"""
        return self.edit("description")

    def edit_due(self):
        """Start editing the due date of the todo"""
        return self.edit("due")

    def edit_scheduled(self):
        """Start editing the scheduled date of the todo"""
        return self.edit("scheduled")

    def edit_recurrence(self):
        """Start editing the recurrence of the todo"""
        return self.edit("recurrence")

    def add_sibling(self):
        """Add a sibling to highlighted item"""
        self.focused.add_sibling()

    def quick_add(self):
        """Type a whole task in one line: project, priority and day"""

        if self.app.bar_switcher.is_focused:
            return

        # Posted at the screen: the overlay covers both panes.
        self.app.screen.post_message(SpawnQuickAdd())

    def toggle_expand(self):
        """Toggle the expansion of the highlighted item"""
        self.focused.toggle_expand()

    def toggle_expand_parent(self):
        """Toggle the expansion of the parent of the highlighted item"""
        self.focused.toggle_expand_parent()

    def is_expanded(self, model: Union[Project, Todo]) -> bool:
        """Whether the panes draw `model` open, with its children on the rows below it"""

        if isinstance(model, Project):
            always = self.vars.always_expand_projects
        else:
            always = self.vars.always_expand_todos

        return always or model.expanded

    def add_child_node(self):
        """Add a child to the highlighted item"""
        self.focused.add_child_node()

    def remove_node(self):
        """Move the highlighted item to the Bin"""
        self.focused.remove_node()

    def delete_node(self):
        """Delete the highlighted item for good (asks first)"""
        self.focused.delete_node()

    def restore_node(self):
        """Restore the highlighted item out of the Bin"""
        self.focused.restore_node()

    def empty_pane(self):
        """Empty the Bin or Completed, whichever is open (asks first)"""

        if self.app.bar_switcher.is_focused:
            return

        tree = self.vars.todos_tree
        model = tree.model if tree is not None else None

        if model is BIN:
            self.empty_bin()
        elif model is COMPLETED:
            self.empty_completed()
        else:
            # Far too much to lose to a chord typed in the wrong pane, so it
            # only works where what it empties is right there on screen.
            self.notify(
                "[b]YY[/b] only empties the Bin ([b]gb[/b]) or Completed ([b]gc[/b])",
                "warning",
            )

    def empty_bin(self):
        """Delete everything in the Bin for good (asks first)"""

        self._empty(
            count=len(binned_tasks()),
            where="in the Bin",
            already="The Bin is already empty",
            done="Bin emptied",
            cancelled="Bin left as it was",
            empty=self._empty_bin,
        )

    def empty_completed(self):
        """Delete every completed task for good (asks first)"""

        self._empty(
            count=len(completed_tasks()),
            where="in Completed",
            already="Completed is already empty",
            done="Completed emptied",
            cancelled="Completed left as it was",
            empty=self._empty_completed,
        )

    def _empty(
        self,
        count: int,
        where: str,
        already: str,
        done: str,
        cancelled: str,
        empty: Callable[[], None],
    ) -> None:
        """Asks before emptying a fixed pane, counting what is about to go"""

        if self.app.bar_switcher.is_focused:
            return

        # Notify rather than confirm on an empty pane, so there's nothing to
        # dismiss for no reason.
        if not count:
            self.notify(already)
            return

        # Unlike other deletes, this isn't tied to the cursor's row, so the
        # confirmation counts what's about to go instead of pointing at it.
        label = "task" if count == 1 else "tasks"
        message = rf"Delete {count} {label} {where} for good? \[y/N]"
        confirmed = f"{done} — {count} {label} deleted"

        if not self.vars.show_confirm:
            empty()
            self.notify(confirmed, "warning")
            return

        self.app.screen.post_message(ShowConfirm(empty, message, confirmed, cancelled))

    def _empty_bin(self) -> None:
        """Empties the Bin; the panes drop the deleted rows from the change signal."""

        empty_bin()

    def _empty_completed(self) -> None:
        """Empties Completed; the panes drop the deleted rows from the change signal."""

        empty_completed()

    def undo(self):
        """Take back the last change made in the panes"""

        self._step_history(forward=False)

    def redo(self):
        """Put back the change that was last taken back"""

        self._step_history(forward=True)

    def _step_history(self, forward: bool) -> None:
        """
        Asks the screen to step through history. Nothing is written here: a
        step can drop the project a pane was built around, and the panes
        belong to the screen, not this API.
        """

        if self.app.bar_switcher.is_focused:
            return

        self.app.screen.post_message(HistoryStep(forward))

    def start_search(self):
        """Find a task anywhere in the tree and jump to it"""

        if self.app.bar_switcher.is_focused:
            return

        # Posted at the screen like quick add: it walks the cursor to whatever
        # gets picked.
        self.app.screen.post_message(SpawnSearch())

    def toggle_complete(self):
        """Toggle the completion of the todo"""
        if isinstance(self.focused, TodosTree):
            self.focused.toggle_complete()

    def set_priority(self, priority: int):
        """Set the priority of the todo (1 is the highest, 0 clears it)"""
        if isinstance(self.focused, TodosTree):
            self.focused.set_priority(priority)

    def set_project_color(self, color: int):
        """Color the project (the same key again takes the color back off)"""
        if isinstance(self.focused, ProjectsTree):
            self.focused.set_color(color)

    def sort_todos(self, mode: TodoSortModeType):
        """Order the todos of a project by priority, due date or scheduled date"""

        tree = self.vars.todos_tree

        # Sort applies to the one todos pane on screen even if projects is focused.
        if tree is None:
            return

        # A fixed project rejects the sort and announces that itself.
        if not tree.sort_by(mode):
            return

        # Nothing on screen shows the sort order, and rows may not visibly
        # move, so confirm via the bar.
        self.notify(f"Todos sorted by [b]{SORT_LABELS[mode]}[/b]")

    def show_note(self):
        """Show and edit the note of the todo"""
        if isinstance(self.focused, TodosTree):
            self.focused.show_note()

    def show_pinned_note(self):
        """Write in the pinned note, which belongs to no task"""

        from todooit.ui.screens import PinnedNoteScreen

        self.app.push_screen(PinnedNoteScreen())

    def open_link(self):
        """Open the first link written in the highlighted row"""

        tree = self.focused

        if tree.highlighted is None:
            return

        link = first_link(tree.current_model.description)

        if link is None:
            self.notify("No link on this row", "warning")
            return

        # The browser opens outside todooit (or fails silently), so the bar
        # confirms which link was opened.
        if open_url(link.url):
            self.notify(f"Opening {link_label(link.url)}")
        else:
            self.notify("Found no browser to open the link with", "error")

    def show_help(self):
        """Show the key bindings in an overlay"""

        # Posted at the screen like every other overlay.
        self.app.screen.post_message(SpawnHelp())
