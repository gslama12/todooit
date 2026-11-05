from datetime import date
from functools import partial
from typing import Optional, Tuple

from rich.markup import escape
from textual import events, on
from textual.containers import Container
from textual.widgets import ContentSwitcher, Static

from todooit.api import (
    TODAY,
    ChangedRows,
    Project,
    Todo,
    fixed_project_from_key,
)
from todooit.api.fixed_projects import project_path
from todooit.api.placement import home_of
from todooit.ui.api.events import (
    BarNotification,
    GotoFixedProject,
    HistoryStep,
    ModeChanged,
    ProjectSelected,
    RevealTodo,
    ShowConfirm,
    SpawnCalendar,
    SpawnHelp,
    SpawnMove,
    SpawnNote,
    SpawnQuickAdd,
    SpawnSearch,
    StartFieldEdit,
)
from todooit.ui.widgets import BarSwitcher, ModelTree
from todooit.ui.widgets.trees import ProjectsTree, TodosTree, make_todos_tree

from .base import BaseScreen
from .calendar import CalendarScreen, calendar_title
from .help import HelpScreen
from .move import Moved, MoveScreen
from .note import NoteScreen
from .quick_add import QuickAdded, QuickAddScreen
from .search import Found, SearchScreen

# Max rows a history step flashes individually; past this, the bar's count
# already says enough and flashing top-to-bottom adds little.
FLASH_LIMIT = 5

# How often, in seconds, the screen looks at whether the date has changed
DAY_TICK = 60


class DualSplit(Container):
    # The split when the projects pane isn't sized to its rows
    FIXED_COLUMNS = "1fr 3fr"

    # What the grid was last set to, so an unchanged width costs no relayout
    _fitted_columns: Optional[str] = None

    DEFAULT_CSS = """
    DualSplit {
        layout: grid;
        grid-size: 2 1;
        grid-columns: 1fr 3fr;

        & > #project_switcher {
            margin-left: 1;
        }

        & > #todo_switcher {
            margin-right: 1;
        }
    }
    """


    def _columns(self) -> str:
        """
        The grid's columns: the projects pane as wide as its widest row needs
        (every project expanded), capped to a share of the screen, and the
        tasks pane taking the rest
        """

        tree = self.query_one(ProjectsTree)
        vars = tree.api.vars

        if not vars.projects_pane_auto_width:
            return self.FIXED_COLUMNS

        switcher = self.query_one("#project_switcher")

        width = tree.outer_width() + switcher.styles.margin.width

        total = self.size.width or self.app.size.width
        cap = int(total * vars.projects_pane_max_width)

        if cap > 0:
            width = min(width, cap)

        return f"{width} 1fr"

    def fit_projects_pane(self) -> None:
        """Resizes the split to the projects pane's rows; a no-op when nothing changed"""

        if not self.is_mounted:
            return

        columns = self._columns()

        if columns != self._fitted_columns:
            self._fitted_columns = columns
            self.styles.grid_columns = columns

    @on(ProjectsTree.Remeasure)
    def _remeasure(self, event: ProjectsTree.Remeasure) -> None:
        event.stop()
        self.fit_projects_pane()

    def on_resize(self, _: events.Resize) -> None:
        # The cap is a share of the screen, so it moves with the terminal
        self.fit_projects_pane()


class MainScreen(BaseScreen):
    DEFAULT_CSS = """
    MainScreen {
        layout: grid;
        grid-size: 1 2;
        grid-rows: 1fr 1;
    }
    """

    def compose(self):
        projects_tree = ProjectsTree(Project._get_or_create_root())

        with DualSplit():
            with ContentSwitcher(id="project_switcher", initial=projects_tree.id):
                yield projects_tree

            # Empty pane shows until a project is opened, or after one is deleted
            with ContentSwitcher(initial="empty-pane", id="todo_switcher"):
                yield Static(id="empty-pane")

        yield BarSwitcher()

    async def handle_key(self, event: events.Key) -> bool:
        # NOTE: Investigate why keys are sent to this screen
        if self.app.screen != self:
            return True

        # Stop the key here so it never reaches Textual's app-level bindings,
        # e.g. ctrl+c's "press ctrl+q to quit" notice popping up unexpectedly
        event.stop()

        self.route_key(self.resolve_key(event))
        return True

    def route_key(self, key: str) -> None:
        """Hand a key to whatever is taking keys now, then record the history step.

        Split out from the event handler so the app can call it directly: a day
        picked off the calendar is settled via the same "enter" path (history
        step included) as one typed by hand.
        """

        # Resolved on the way in: a focused bar wants the character pressed,
        # not the key's name
        if self.app.bar_switcher.is_focused:
            self.app.bar_switcher.handle_keypress(key)
        else:
            self.api.handle_key(key)

        self.record_change()

    @property
    def mid_edit(self) -> bool:
        """Whether any pane's tree is mid-edit right now.

        Asked of the trees, not the focus: an edit on a column the pane has no
        room for is drawn in the bar (which then holds focus), but the edit
        itself still belongs to the tree.
        """

        # Only panes in front: a hidden one isn't where an edit happens
        return any(tree.is_editing for tree in self.query(ModelTree) if tree.display)

    def record_change(self) -> None:
        """Record what the key just pressed left different, unless mid-edit,
        and redraw every pane from it.

        A new row is written to the DB before it has a name, so recording per
        keystroke would split "add a task" into separate undo steps (`n`, the
        typed name, enter).
        """

        if self.mid_edit:
            return

        changed = self.api.history.record()

        if changed:
            self.refresh_panes(changed)

    @on(events.ScreenResume)
    def resumed(self, _: events.ScreenResume) -> None:
        """Record changes made by an overlay (note, quick-add, move) now that it's closed.

        Those screens write to the DB directly, bypassing `handle_key` here, so
        this is the first chance to record them.
        """

        self.record_change()

    @on(HistoryStep)
    def history_step(self, event: HistoryStep) -> None:
        """Walk one step back through the history, or one step forward."""

        step = self.api.history.redo if event.forward else self.api.history.undo
        restored = step()

        if restored is None:
            way = "redo" if event.forward else "undo"
            self.api.notify(f"Nothing left to {way}", "warning")
            return

        self.refresh_panes(restored)

        # Flash touched rows like a revived project, but only while there are
        # few enough for flashing to mean anything
        touched = restored.touched

        if len(touched) <= FLASH_LIMIT:
            for tree in self.query(ModelTree):
                for uuid in touched:
                    tree.flash_row_if_shown(uuid)

        done = "Redone" if event.forward else "Undone"
        self.api.notify(f"{done} — {restored.summary()}")

    def refresh_panes(self, changed: ChangedRows) -> None:
        """Redraw every pane from the rows one key (or history step) changed.

        The one place panes refresh after a model change: a todo can be shown
        in several panes at once (its project plus any fixed project gathering
        it), so all of them redraw, whichever code made the change. Order
        matters: rows and panes of gone models are dropped first (a renderer
        outliving its row reads a deleted table row), then the rest redraw.
        """

        dropped = [self.drop_project_pane(uuid) for uuid in changed.gone]

        for tree in self.query(ModelTree):
            tree.forget_rows(changed.gone)

            if tree not in dropped:
                tree.force_refresh()

    @on(BarNotification)
    def show_notification(self, event: BarNotification):
        self.app.bar_switcher.switch_to_notification(event)

    @on(SpawnHelp)
    def spawn_help(self, _: SpawnHelp) -> None:
        self.app.push_screen(HelpScreen())

    @on(SpawnNote)
    def spawn_note(self, event: SpawnNote) -> None:
        self.open_note(event.todo)

    def open_note(self, todo: Todo, at: Optional[Tuple[int, int]] = None) -> None:
        self.app.push_screen(NoteScreen(todo, at=at), self.note_closed)

    def note_closed(self, _: None) -> None:
        """Redraw the rows' note icons.

        Note text is left out of the undo history, so `record_change` sees no
        change when only the text was edited and wouldn't redraw anything.
        """

        self.refresh_panes(ChangedRows())

    @on(SpawnQuickAdd)
    def spawn_quick_add(self, _: SpawnQuickAdd) -> None:
        """Open the one-line quick-add entry over the app.

        The fallback project is resolved here, not inside the overlay: once
        it's up, the panes it would need to ask are behind it.
        """

        project = self.api.vars.current_project

        self.app.push_screen(
            QuickAddScreen(project if isinstance(project, Project) else None),
            self.quick_add_done,
        )

    async def quick_add_done(self, result: Optional[QuickAdded]) -> None:
        """Point the cursor at a task just added via quick-add, wherever it landed,
        and tell the bar which project took it.
        """

        if result is None:
            return

        todo = result.todo
        project = todo.parent_project

        if result.project_created and project is not None:
            self.reveal_project(project)

        await self.reveal_todo(todo)

        what = escape(todo.description)

        # Destination is left out only when there's no project to name
        if project is None:  # pragma: no cover
            message = f"Added [b]{what}[/b]"
        else:
            where = escape(project.description)
            into = "to new project" if result.project_created else "to"
            message = f"Added [b]{what}[/b] {into} [b]{where}[/b]"

        self.post_message(BarNotification(message, "info"))

    def reveal_project(self, project: Project) -> None:
        """Bring a newly created project into view and flash it.

        Expands its ancestors first since a nested project is only reachable
        once its parents are open.
        """

        tree = self.api.vars.projects_tree
        parent = project.parent_project

        while parent is not None and not parent.is_root:
            parent.set_expanded(True)
            parent = parent.parent_project

        tree.force_refresh()
        tree.flash_row(project.uuid)

    @on(SpawnCalendar)
    def spawn_calendar(self, event: SpawnCalendar) -> None:
        """Open the calendar over the date field that requested it.

        Which tree/column rides on the event, since the field stays mid-edit
        behind the overlay and can't be queried once it's up.
        """

        self.app.push_screen(
            CalendarScreen(calendar_title(event.column), event.initial),
            partial(self.calendar_done, event.tree, event.column),
        )

    def calendar_done(
        self, tree: ModelTree, column: str, day: Optional[date]
    ) -> None:
        """Buffer the picked day, then replay "enter" so it goes through the same
        validation/notification/teardown path as a typed date.
        """

        if day is None:
            return

        if tree.take_picked_day(column, day):
            self.route_key("enter")

    @on(SpawnMove)
    def spawn_move(self, event: SpawnMove) -> None:
        self.app.push_screen(MoveScreen(event.todo), self.move_done)

    async def move_done(self, result: Optional[Moved]) -> None:
        """Follow a moved task into its new project: point the cursor at it and
        tell the bar which project took it.
        """

        if result is None:
            return

        todo, project = result

        await self.reveal_todo(todo)

        what = escape(todo.description)
        where = escape(project_path(project))

        self.post_message(
            BarNotification(f"Moved [b]{what}[/b] to [b]{where}[/b]", "info")
        )

    @on(SpawnSearch)
    def spawn_search(self, _: SpawnSearch) -> None:
        self.app.push_screen(SearchScreen(), self.search_done)

    async def search_done(self, found: Optional[Found]) -> None:
        if found is None:
            return

        await self.reveal_todo(found.todo)

        # A hit inside a note opens that note at the matching line
        if found.hit is not None:
            hit = found.hit
            self.open_note(found.todo, at=(hit.row, hit.column))

    @on(RevealTodo)
    async def reveal_moved_todo(self, event: RevealTodo) -> None:
        """Follow a task that just left its only pane (e.g. untick in completion log,
        restore from Bin) by revealing it where it landed, same as the finder does.
        """

        await self.reveal_todo(event.todo)

    async def reveal_todo(self, todo: Todo) -> None:
        """Point the cursor at a task found elsewhere, expanding every ancestor
        project and step needed to reach it.

        Projects pane is moved to the project first: it re-emits `ProjectSelected`
        on redraw, which would otherwise snap the tasks pane back to a stale project.
        """

        project = home_of(todo)

        if project is None:  # pragma: no cover
            return

        projects_tree = self.api.vars.projects_tree
        parent = project.parent_project

        while parent is not None and not parent.is_root:
            parent.set_expanded(True)
            parent = parent.parent_project

        projects_tree.force_refresh()
        projects_tree.highlight_id_if_shown(project.uuid)

        tree = await self.show_project(project)

        for step in todo.ancestors:
            step.set_expanded(True)

        tree.force_refresh()
        self.app.set_focus(tree)

        # After focus (which puts the cursor on the pane's first row) so the
        # flash can override it to the row that was actually asked for
        self.point_at(tree, todo)

    @staticmethod
    def point_at(tree: TodosTree, todo: Todo) -> None:
        """Put the cursor on a task, or the nearest ancestor drawn in the pane
        (fixed panes gather whole tasks, not their steps).
        """

        for node in [todo, *todo.ancestors]:
            if tree.highlight_id_if_shown(node.uuid):
                tree.flash_row(node.uuid)
                return

    @on(StartFieldEdit)
    def start_field_edit(self, event: StartFieldEdit):
        self.app.bar_switcher.switch_to_field(event.tree, event.column)

    @on(ShowConfirm)
    def show_confirm(self, event: ShowConfirm):
        self.app.bar_switcher.switch_to_confirm(event)
        self.post_message(ModeChanged("CONFIRM"))

    def drop_project_pane(self, uuid: str) -> Optional[TodosTree]:
        """Drop the pane of a deleted project, falling back to the empty pane.

        Takes a uuid, not the project object: by the time the change signal
        names a project as gone, it's a gone row rather than a live object.
        Returns the pane on its way out, if there was one.
        """

        switcher = self.query_one("#todo_switcher", expect_type=ContentSwitcher)
        panes = switcher.query(f"#TodosTree_{uuid}")

        if not panes:
            return None

        pane = panes.first(TodosTree)
        if switcher.current == pane.id:
            switcher.current = "empty-pane"

        pane.remove()
        return pane

    async def show_project(self, project) -> TodosTree:
        """Bring the project's tasks pane to the front, building it if needed."""

        switcher = self.query_one("#todo_switcher", expect_type=ContentSwitcher)
        tree = make_todos_tree(project)

        existing = switcher.query(f"#{tree.id}")
        if not existing:
            await switcher.add_content(tree, set_current=True)
            # Was mounted out of sight, so its first draw was deferred
            tree.refresh_if_dirty()
            return tree

        switcher.current = tree.id

        # Refreshed here, not via the switcher's `Show` (arrives a tick late) --
        # the caller places the cursor as soon as this returns
        shown = existing.first(TodosTree)
        shown.refresh_if_dirty()
        return shown

    @on(ProjectSelected)
    async def project_selected(self, event: ProjectSelected):
        await self.show_project(event.project)

    @on(GotoFixedProject)
    async def goto_fixed_project(self, event: GotoFixedProject) -> None:
        """Move to a fixed project and focus its first task.

        The pane is brought up here rather than via the `ProjectSelected` the
        highlight fires, so there's something to focus immediately.
        """

        project = fixed_project_from_key(event.key)
        if project is None:  # pragma: no cover
            return

        self.api.vars.projects_tree.highlight_id(project.uuid)

        tree = await self.show_project(project)
        tree.focus()
        tree.action_first()

    def on_mount(self):
        # Opens on today's tasks; deferred until after the first refresh so
        # the config gets to configure the panes first
        self.call_after_refresh(
            lambda: self.post_message(GotoFixedProject(TODAY.key))
        )

        self._day = date.today()
        self.set_interval(DAY_TICK, self.refresh_on_new_day)

    def refresh_on_new_day(self) -> None:
        """Redraw every pane once the date has changed.

        Today and Upcoming gather their rows by the date, but nothing happens
        in the app at midnight to redraw them. Holds off during an edit or
        under an overlay, and tries again on the next tick.
        """

        if self.app.screen is not self or self.mid_edit:
            return

        today = date.today()

        if today != self._day:
            self._day = today
            self.refresh_panes(ChangedRows())
