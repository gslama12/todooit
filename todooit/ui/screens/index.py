from datetime import date
from functools import partial
from typing import Optional, Type
from rich.markup import escape
from sqlalchemy.event import listen
from sqlalchemy.orm.attributes import get_history
from textual import events, on
from textual.containers import Container
from textual.widgets import ContentSwitcher
from todooit.api import (
    BIN,
    COMPLETED,
    TODAY,
    Restored,
    Todo,
    Project,
    fixed_project_from_key,
)
from todooit.api.model import DooitModel
from todooit.ui.api.events import (
    DooitEvent,
    ModeChanged,
    ShowConfirm,
    StartFieldEdit,
    StartSort,
    TodoChanged,
    TodoDescriptionChanged,
    TodoDueChanged,
    TodoNoteChanged,
    TodoScheduledChanged,
    TodoAgentChanged,
    TodoRecurrenceChanged,
    TodoStatusChanged,
    TodoPriorityChanged,
    ProjectChanged,
    ProjectDescriptionChanged,
    ProjectRemoved,
    ProjectSelected,
    RevealTodo,
    GotoFixedProject,
    HistoryStep,
    SpawnHelp,
    SpawnMove,
    SpawnNote,
    SpawnCalendar,
    SpawnQuickAdd,
    SpawnSearch,
    BarNotification,
)
from todooit.api.fixed_projects import owning_project, project_path
from todooit.ui.api.events.events import ProjectType
from todooit.ui.widgets.trees import ProjectsTree, TodosTree, make_todos_tree
from todooit.ui.widgets import BarSwitcher, Dashboard, ModelTree
from .base import BaseScreen
from .calendar import CalendarScreen, calendar_title
from .move import Moved, MoveScreen
from .note import NoteScreen
from .quick_add import QuickAdded, QuickAddScreen
from .search import SearchScreen, task_root


# How many rows one history step is willing to point out one at a time.
# Past that the bar has already said how much moved, and panes lighting up
# from top to bottom say less than the count does.
FLASH_LIMIT = 5


class DualSplit(Container):
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

            with ContentSwitcher(initial="dooit-dashboard", id="todo_switcher"):
                yield Dashboard(id="dooit-dashboard")

        yield BarSwitcher()

    async def handle_key(self, event: events.Key) -> bool:
        # NOTE: Investigate why keys are sent to this screen
        if self.app.screen != self:
            return True

        # Every key on this screen is dooit's own. Stopping it here is what
        # keeps it away from the bindings textual keeps at the app level --
        # ctrl+c among them, which is bound to a "press ctrl+q to quit" notice
        # that would otherwise turn up on top of the copy it just did
        event.stop()

        await self.route_key(self.resolve_key(event))
        return True

    async def route_key(self, key: str) -> None:
        """
        Hand a key to whatever is taking keys right now, and write down what
        it left different

        Split out from the event so that the app can send itself one: a date
        picked off the calendar is settled by the very enter a hand would have
        pressed, and it has to go the same way that enter would have gone --
        the history step included, or a day picked off the month would be the
        one change in the app that nothing could undo.
        """

        # Resolved on the way in rather than per bar: a bar that is typed into
        # wants the character that was pressed, not the name of the key
        if self.app.bar_switcher.is_focused:
            await self.app.bar_switcher.handle_keypress(key)
        else:
            await self.api.handle_key(key)

        self.record_change()

    @property
    def mid_edit(self) -> bool:
        """
        Whether a row is being typed into right now, in any of the panes

        Asked of the trees rather than of the focus: an edit on a column the
        pane has no room for is drawn in the bar, and the bar is what holds
        the focus while it runs, but the edit itself is still the tree's.
        """

        # Only the panes in front: one behind them is not being typed into,
        # and a pane still owed a redraw can be holding a row whose model has
        # gone, which asking it what it is editing would go looking for
        return any(tree.is_editing for tree in self.query(ModelTree) if tree.display)

    def record_change(self) -> None:
        """
        Hands the history whatever the key just pressed left different

        Nothing is recorded in the middle of an edit. A new row is written to
        the database the moment it is made — before it has been given a name
        — so a change taken at every keystroke would leave `n`, the name, and
        the enter that keeps it as separate things to undo, when what was done
        was to add one task.
        """

        if not self.mid_edit:
            self.api.history.record()

    @on(events.ScreenResume)
    def resumed(self, _: events.ScreenResume) -> None:
        """
        Records what a window that was open over the panes changed

        The note, the one line entry and the move window all write to the
        database and are gone by the time the panes are back, so their keys
        never reached `handle_key` here. Coming back into view is the moment
        there is something to record.
        """

        self.record_change()

    @on(HistoryStep)
    async def history_step(self, event: HistoryStep) -> None:
        """
        Walks one step back through the history, or one step forward
        """

        step = self.api.history.redo if event.forward else self.api.history.undo
        restored = step()

        if restored is None:
            way = "redo" if event.forward else "undo"
            self.api.notify(f"Nothing left to {way}", "warning")
            return

        await self.rebuild_after(restored)

        done = "Redone" if event.forward else "Undone"
        self.api.notify(f"{done} — {restored.summary()}")

    async def rebuild_after(self, restored: Restored) -> None:
        """
        Puts the panes back together over the rows a history step left

        The order is what matters. Nothing drawn from a row that has just left
        the database can be kept — a renderer outliving its row is a row read
        back out of a table it is no longer in — so the panes let go of those
        first, the ones built around a project that is gone are dropped whole,
        and only then is anything redrawn.
        """

        for tree in self.query(ModelTree):
            tree.forget_rows(restored.gone)

        for uuid in restored.gone:
            await self.drop_project_pane(uuid)

        for tree in self.query(ModelTree):
            tree.force_refresh()

        # A step can land in a pane that is not in front, or leave a row
        # looking exactly as it did in the one that is; the rows it wrote are
        # pointed out the same way a revived project is, while there are few
        # enough of them for pointing to mean anything
        touched = restored.touched

        if len(touched) <= FLASH_LIMIT:
            for tree in self.query(ModelTree):
                for uuid in touched:
                    tree.flash_row_if_shown(uuid)

    @on(BarNotification)
    def show_notification(self, event: BarNotification):
        self.app.bar_switcher.switch_to_notification(event)

    @on(SpawnHelp)
    async def spawn_help(self, _: SpawnHelp) -> None:
        self.app.push_screen("help")

    @on(SpawnNote)
    def spawn_note(self, event: SpawnNote) -> None:
        self.app.push_screen(NoteScreen(event.todo))

    @on(SpawnQuickAdd)
    def spawn_quick_add(self, _: SpawnQuickAdd) -> None:
        """
        Opens the one line task entry over the app

        The project the line falls back to is worked out here rather than
        inside the overlay: once the overlay is up it is the screen, and the
        panes it would have to ask are behind it.
        """

        project = self.api.vars.current_project

        self.app.push_screen(
            QuickAddScreen(project if isinstance(project, Project) else None),
            self.quick_add_done,
        )

    async def quick_add_done(self, result: Optional[QuickAdded]) -> None:
        """
        Puts the cursor on a task that was added from somewhere else

        The task can have landed in a project nobody is looking at, which is
        the pane the cursor is taken to: a task typed in one line is one the
        next keypress is meant for, so it is left pointed at the same way a
        task found with the finder is. The bar still says where it went, since
        the panes moving underneath is not on its own an answer to which
        project took it.
        """

        if result is None:
            return

        todo = result.todo
        project = todo.parent_project

        if result.project_created and project is not None:
            self.reveal_project(project)

        self.post_message(TodoChanged(todo))
        await self.reveal_todo(todo)

        what = escape(todo.description)

        # Where it went is half of what the line is being told, so it is only
        # left out when there is no project to name
        if project is None:  # pragma: no cover
            message = f"Added [b]{what}[/b]"
        else:
            where = escape(project.description)
            into = "to new project" if result.project_created else "to"
            message = f"Added [b]{what}[/b] {into} [b]{where}[/b]"

        self.post_message(BarNotification(message, "info"))

    def reveal_project(self, project: Project) -> None:
        """
        Brings a project that has just been built into view, and flashes it

        The same thing that happens to a project rebuilt to take a task back
        out of the Bin: a new row appears among ones that were already there,
        and the flash is what says which of them is the new one. A project
        made inside another is only reachable once that one is open, so its
        parents are expanded before the pane is redrawn.
        """

        tree = self.api.vars.projects_tree
        parent = project.parent_project

        while parent is not None and not parent.is_root:
            tree.expanded_nodes[parent.uuid] = True
            parent = parent.parent_project

        tree.force_refresh()
        tree.flash_row(project.uuid)

    @on(SpawnCalendar)
    def spawn_calendar(self, event: SpawnCalendar) -> None:
        """
        Opens the month over the date field that asked for it

        The field stays mid-edit behind the window, so what comes back has
        somewhere to land: which tree and which column that is rides along on
        the event, since a window covering the panes cannot ask them.
        """

        self.app.push_screen(
            CalendarScreen(calendar_title(event.column), event.initial),
            partial(self.calendar_done, event.tree, event.column),
        )

    async def calendar_done(
        self, tree: ModelTree, column: str, day: Optional[date]
    ) -> None:
        """
        Keeps the day that was picked, exactly as a typed one is kept

        The day goes into the buffer and the app then sends itself the enter
        that settles it, so a date picked off the month runs through the same
        column check, the same notification on a date a todo may not have, and
        the same bar teardown as one typed by hand.
        """

        if day is None:
            return

        if tree.take_picked_day(column, day):
            await self.route_key("enter")

    @on(SpawnMove)
    def spawn_move(self, event: SpawnMove) -> None:
        self.app.push_screen(MoveScreen(event.todo), self.move_done)

    async def move_done(self, result: Optional[Moved]) -> None:
        """
        Follows a task into the project it has just been filed under

        The task is gone from the pane it was moved out of and is the last row
        of one nobody is looking at, so the cursor is taken over to it the same
        way it is taken to a task typed in from somewhere else: what was just
        moved is what the next keypress is meant for. The bar still says where
        it went, since the panes rearranging underneath is not on its own an
        answer to which project took it.
        """

        if result is None:
            return

        todo, project = result

        self.post_message(TodoChanged(todo))
        await self.reveal_todo(todo)

        what = escape(todo.description)
        where = escape(project_path(project))

        self.post_message(
            BarNotification(f"Moved [b]{what}[/b] to [b]{where}[/b]", "info")
        )

    @on(SpawnSearch)
    def spawn_search(self, _: SpawnSearch) -> None:
        self.app.push_screen(SearchScreen(), self.search_done)

    async def search_done(self, todo: Optional[Todo]) -> None:
        if todo is not None:
            await self.reveal_todo(todo)

    @on(RevealTodo)
    async def reveal_moved_todo(self, event: RevealTodo) -> None:
        """
        Goes after a task that has just left the pane it was being read in

        Unticking a row in the completion log, or taking one back out of the
        Bin, drops it out of the only pane it was in: what the key did is off
        screen the moment it lands. So the same arrival the finder makes is
        made for it — the project is opened, the cursor put on the row, the
        row flashed — and where the task went is where the cursor now is.
        """

        await self.reveal_todo(event.todo)

    async def reveal_todo(self, todo: Todo) -> None:
        """
        Puts the cursor on a task that was found from somewhere else

        The task can be anywhere: inside a project nobody has opened, under a
        project that is not even unfolded, filed as a step of another task. So
        the way down to it is opened a level at a time -- the projects above
        it in the left hand pane, the tasks above it in the right hand one --
        before the row can be pointed at.

        The projects pane is moved onto the project first. It re-emits
        `ProjectSelected` whenever it is redrawn, and a pane left highlighting
        something else would take the tasks pane back to it the moment
        anything changed.
        """

        project = self.pane_of(todo)

        if project is None:  # pragma: no cover
            return

        projects_tree = self.api.vars.projects_tree
        parent = project.parent_project

        while parent is not None and not parent.is_root:
            projects_tree.expanded_nodes[parent.uuid] = True
            parent = parent.parent_project

        projects_tree.force_refresh()
        projects_tree.highlight_id_if_shown(project.uuid)

        tree = await self.show_project(project)

        step = todo.parent_todo
        while step is not None:
            tree.expanded_nodes[step.uuid] = True
            step = step.parent_todo

        tree.force_refresh()
        self.app.set_focus(tree)

        # After the focus, which puts the cursor on the first row of a pane
        # that had none; and the flash last, so the row says which of them was
        # the one that was asked for
        self.point_at(tree, todo)

    @staticmethod
    def pane_of(todo: Todo) -> Optional[ProjectType]:
        """
        The pane a task is to be found in

        Its own project while there is work left in it. A task that is over
        with has left that pane for one of the fixed ones -- finished for
        Completed, thrown away for the Bin -- and is only drawn there.
        """

        if todo.is_binned:
            return BIN

        if not task_root(todo).pending:
            return COMPLETED

        return owning_project(todo)

    @staticmethod
    def point_at(tree: TodosTree, todo: Todo) -> None:
        """
        Puts the cursor on a task, or on the nearest thing to it that is drawn

        A pane need not have a row for the task itself: the fixed ones gather
        whole tasks, and a step of one is only in there inside its parent. The
        parent is where the cursor stops in that case, which is as close to
        the step as that pane goes.
        """

        node: Optional[Todo] = todo

        while node is not None:
            if tree.highlight_id_if_shown(node.uuid):
                tree.flash_row(node.uuid)
                return

            node = node.parent_todo

    @on(StartFieldEdit)
    def start_field_edit(self, event: StartFieldEdit):
        self.app.bar_switcher.switch_to_field(event.tree, event.column)

    @on(StartSort)
    def start_sort(self, event: StartSort):
        self.app.bar_switcher.switch_to_sort(event.model, event.callback)
        self.post_message(ModeChanged("SORT"))

    @on(ShowConfirm)
    def show_confirm(self, event: ShowConfirm):
        self.app.bar_switcher.switch_to_confirm(event)
        self.post_message(ModeChanged("CONFIRM"))

    @on(ProjectRemoved)
    async def project_removed(self, event: ProjectRemoved):
        await self.drop_project_pane(event.project.uuid)

    async def drop_project_pane(self, uuid: str) -> None:
        """
        Drops the pane of a project that is gone

        Nothing highlights the pane back into place when the project it
        belongs to was the last one, so it is swapped for the dashboard rather
        than left showing (and collecting todos for) a deleted project.

        Named by uuid rather than handed the project: a project taken away by
        a history step is a row, not an object, by the time the pane it left
        behind has to go.
        """

        switcher = self.query_one("#todo_switcher", expect_type=ContentSwitcher)
        panes = switcher.query(f"#TodosTree_{uuid}")

        if not panes:
            return

        pane = panes.first()
        if switcher.current == pane.id:
            switcher.current = "dooit-dashboard"

        await pane.remove()

    async def show_project(self, project) -> TodosTree:
        """
        Brings the project's tasks pane to the front, building it if need be
        """

        switcher = self.query_one("#todo_switcher", expect_type=ContentSwitcher)
        tree = make_todos_tree(project)

        existing = switcher.query(f"#{tree.id}")
        if not existing:
            await switcher.add_content(tree, set_current=True)
            # Mounted out of sight, so the pane's own first draw was put off
            tree.refresh_if_dirty()
            return tree

        switcher.current = tree.id

        # Here rather than off the `Show` the switcher's flip sends: that
        # arrives a tick later, and the caller puts the cursor on a row the
        # moment this returns. Whatever changed while the pane was behind is
        # drawn before anybody can look at it
        shown = existing.first(TodosTree)
        shown.refresh_if_dirty()
        return shown

    @on(ProjectSelected)
    async def project_selected(self, event: ProjectSelected):
        await self.show_project(event.project)

    @on(GotoFixedProject)
    async def goto_fixed_project(self, event: GotoFixedProject) -> None:
        """
        Moves onto a fixed project and hands the focus to its first task

        The pane is brought up here rather than left to the `ProjectSelected`
        the highlight sends off, so that there is something to focus by the
        time the cursor is put on the first todo.
        """

        project = fixed_project_from_key(event.key)
        if project is None:  # pragma: no cover
            return

        self.api.vars.projects_tree.highlight_id(project.uuid)

        tree = await self.show_project(project)
        tree.focus()
        tree.action_first()

    @on(TodoChanged)
    @on(ProjectChanged)
    def model_changed(self, _: DooitEvent) -> None:
        """
        Redraws every pane once something has actually changed

        A todo is no longer in one place only: it is in the pane of the project
        it is filed under, and in every fixed project that gathered it up. A
        pane that is not in front goes on drawing whatever it was built with,
        so an edit made in one of them would leave the others saying the old
        thing until they happened to be rebuilt. All of them are refreshed
        together, which also settles what a fixed project shows and in what
        order, neither of which the edited row alone can say.

        Only the events that write a model back come through here; the ones
        that say where the cursor is do not, or this would run per keystroke.
        """

        for tree in self.query(ModelTree):
            tree.force_refresh()

    # SQLAlchemy event listeners

    def _track_field(
        self, table: Type[DooitModel], field: str, event: Type[DooitEvent]
    ) -> None:
        def track(_mapper, _connection, target: Todo):
            history = get_history(target, field)
            if history.has_changes():
                old = history.deleted[0] if history.deleted else ""
                new = history.added[0] if history.added else ""

                if old or new:
                    self.post_message(
                        event(old, new, target),
                    )

        listen(table, "after_update", track)

    def on_mount(self):
        # Dooit opens on the day's work: the tasks scheduled for today, with
        # the cursor already on the first of them. Left until after the first
        # refresh, so that the config has had its say about the panes first.
        self.call_after_refresh(
            lambda: self.post_message(GotoFixedProject(TODAY.key))
        )

        listeners = (
            (Project, "description", ProjectDescriptionChanged),
            (Todo, "description", TodoDescriptionChanged),
            (Todo, "due", TodoDueChanged),
            (Todo, "scheduled", TodoScheduledChanged),
            (Todo, "agent", TodoAgentChanged),
            (Todo, "recurrence", TodoRecurrenceChanged),
            (Todo, "pending", TodoStatusChanged),
            (Todo, "priority", TodoPriorityChanged),
            (Todo, "note", TodoNoteChanged),
        )

        for table, field, event in listeners:
            self._track_field(table, field, event)
