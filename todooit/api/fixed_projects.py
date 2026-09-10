"""
Projects that are part of the app rather than of the database

A fixed project is always in the projects pane: it cannot be created, renamed,
moved or deleted, and it owns no todos of its own. What it shows is gathered
from the real projects every time it is asked, which is what lets "Today" pull
one day's work out of the whole tree.

Everything the trees and the status bar read off a `Project` is answered here
too, so a fixed project can be handed around in place of a stored one; what
tells them apart is `is_fixed`, and the `icon` each one is drawn with.

To add another one: subclass `FixedProject`, give it a key, a title, an icon
and a `todo_groups`, and register an instance of it below.
"""

from dataclasses import dataclass, field
from datetime import date, datetime, time, timedelta
from typing import Dict, Iterator, List, Optional, Tuple

from sqlalchemy import select

from ..utils.day_names import day_label
from .manager import manager
from .project import Project
from .todo import Todo, priority_key

FIXED_ID_PREFIX = "FixedProject"

# What separates the steps of a project path in a group heading. A chevron
# rather than a slash: the paths sit in prose-like headings, not in a shell
PATH_SEPARATOR = " › "


@dataclass
class TodoRow:
    """
    One row of a block, and whatever the block draws underneath it

    A row that is the work itself is drawn like a todo anywhere else: the
    steps filed under it hang off it, as far as it is expanded, and `under`
    is empty because the pane works that out for itself.

    A context row is a task carrying no day of its own, drawn only to say
    what the work beneath it belongs to. There the block picked what hangs
    off it — the way down to the todos it gathered, and nothing else — which
    is what `under` holds.
    """

    todo: Todo
    under: List["TodoRow"] = field(default_factory=list)
    is_context: bool = False


@dataclass
class TodoGroup:
    """
    A block of todos shown under one heading

    A blank label means the block stands on its own and needs no heading.

    `todos` is the work the block gathered; `rows` is how that work is drawn,
    which is the same thing flat unless the block had to reach it through
    tasks that carry no day of their own.
    """

    todos: List[Todo]
    label: str = ""
    rows: List[TodoRow] = field(default_factory=list)

    def __post_init__(self) -> None:
        if not self.rows:
            self.rows = [TodoRow(todo) for todo in self.todos]


def owning_project(todo: Todo) -> Optional[Project]:
    """
    The project a todo is filed under, however deeply it is nested inside it
    """

    node = todo
    while node.parent_project is None and node.parent_todo is not None:
        node = node.parent_todo

    return node.parent_project


def _ancestor_todos(todo: Todo) -> Iterator[Todo]:
    """
    Every todo the given one is a step of, the nearest one first
    """

    node = todo.parent_todo

    while node is not None:
        yield node
        node = node.parent_todo


def task_roots(todos: List[Todo]) -> List[Todo]:
    """
    The gathered todos that no other gathered todo is filed under

    A pane draws a row with the steps of it underneath, so a step whose task
    was gathered too is already on screen inside that task; gathering it again
    would draw it twice over, once under its parent and once beside it. What
    comes back is one row per family, and every other match is reached by
    opening the row it belongs to.

    A step whose task was *not* gathered stands as a row of its own: nothing
    above it was scheduled, so nothing above it is in the pane, and the step
    is the whole of what the day has to say about that task.
    """

    gathered = {todo.id for todo in todos}

    return [
        todo
        for todo in todos
        if not any(parent.id in gathered for parent in _ancestor_todos(todo))
    ]


def _rows_with_context(gathered: List[Todo]) -> List[TodoRow]:
    """
    The gathered todos, each drawn under the tasks it is a step of

    A step planned on its own is still its task's work, and a pane that
    dropped the task would show a row with nothing to say what it is part of.
    So the tasks above it come along, drawn for context alone, with only the
    steps the block actually gathered underneath them.

    Nothing gathered is ever context: a task that was planned itself was
    gathered, and everything filed under it came along with it rather than
    being picked out one step at a time.

    A task two of whose steps land in the same block is drawn once, with both
    of them under it, and keeps the place of whichever came first.
    """

    rows: Dict[int, TodoRow] = {}
    tops: List[TodoRow] = []

    def row_for(todo: Todo, is_context: bool) -> TodoRow:
        row = rows.get(todo.id)

        if row is not None:
            return row

        row = TodoRow(todo, is_context=is_context)
        rows[todo.id] = row

        parent = todo.parent_todo

        if parent is None:
            tops.append(row)
        else:
            row_for(parent, True).under.append(row)

        return row

    for todo in gathered:
        row_for(todo, False)

    return tops


# How a day's work is read: whatever slipped into it first, and each of the
# two runs by priority. Work that was planned for a day already gone by is the
# first thing the day has to decide about — pick it up now, or plan it for
# another day — and it is what the panes are opened to be rid of, so it is not
# left to be hunted for among the work that belongs to the day
def slipped_first(todo: Todo) -> tuple:
    return (not todo.is_overscheduled,) + priority_key(todo)


def scheduled_group(todos: List[Todo], label: str = "") -> TodoGroup:
    """
    A block of the work planned for one day, the most pressing of it first

    What a day asks is what to do first, so the rows it gathered are read by
    what has already slipped and then by priority; the tasks drawn above them
    for context keep the place of the most pressing thing underneath them,
    since that is what the block is really ordering.
    """

    gathered = sorted(task_roots(todos), key=slipped_first)

    return TodoGroup(
        todos=gathered,
        label=label,
        rows=_rows_with_context(gathered),
    )


def project_path(project: Project) -> str:
    """
    The project's name, preceded by the names of every project it sits in
    """

    parts = []
    node: Optional[Project] = project

    while node is not None and not node.is_root:
        parts.append(node.description)
        node = node.parent_project

    return PATH_SEPARATOR.join(reversed(parts))


def _project_order() -> Dict[int, int]:
    """
    Where each project falls when the tree is read top to bottom

    Group blocks follow the projects pane rather than an order of their own, so
    that a heading is found where its project is.
    """

    order: Dict[int, int] = {}

    def walk(project: Project) -> None:
        for child in project.projects:
            order[child.id] = len(order)
            walk(child)

    walk(Project._get_or_create_root())
    return order


class FixedProject:
    """
    Base class for the projects that are always there
    """

    key: str = ""
    title: str = ""
    # Drawn in front of the name, where a regular project gets its folder
    icon: str = ""

    is_fixed: bool = True

    # Whether the project is pinned to the foot of the projects pane rather
    # than opening it. For the one nothing is planned in: what is already done
    # belongs under the work still to do, not above it
    pinned_bottom: bool = False

    # Whether the row is drawn in gray rather than in the accent the fixed
    # projects otherwise get. For a project that is there to be looked
    # something up in now and then, and never worked out of
    muted: bool = False

    # Whether a row should say which project it was pulled out of. One that
    # opens a block per project has already said so in the heading; one
    # grouped by anything else would otherwise lose that entirely
    show_owning_project: bool = False

    # Columns the headings have already said, and which the rows underneath
    # them need not repeat. They can still be edited: the buffer is drawn in
    # the bar rather than in a column the pane does not have
    hidden_columns: Tuple[str, ...] = ()

    # Columns the pane draws on top of the ones the layout asks for, in place
    # of whatever it hid. They go in right after the description, where the
    # columns they stand in for would have been
    extra_columns: Tuple[str, ...] = ()

    # Date columns to draw as a day alone. A pane that is read a day at a time
    # has no use for the hour, which only crowds the columns beside it
    day_only_columns: Tuple[str, ...] = ()

    # Whether a row unticked in here is held in its place until the edit that
    # follows has been confirmed, rather than leaving the moment it stops
    # being what the project gathers
    holds_unticked_rows: bool = False

    # Whether what the project gathers is the todos that have been thrown
    # away. Every other pane shows the ones that have not: a binned todo is in
    # here and nowhere else, until it is restored or deleted for good
    gathers_binned: bool = False

    # Whether a row planned for a day already gone by is marked as such. Only
    # the panes that carry such work onto today have anything to mark: they
    # draw it among the day's own work, and the mark is what tells the two
    # apart — and says which day it was that the row was missed on
    marks_overscheduled: bool = False

    # --- the parts of `Project` the trees and the bar read ---

    is_root: bool = False
    order_index: int = -1
    nest_level: int = 0
    parent_project: Optional[Project] = None
    parent: Optional[Project] = None
    projects: List[Project] = []
    total_projects: int = 0

    @property
    def id(self) -> str:
        return self.key

    @property
    def uuid(self) -> str:
        return f"{FIXED_ID_PREFIX}_{self.key}"

    @property
    def description(self) -> str:
        return self.title

    @property
    def todo_groups(self) -> List[TodoGroup]:
        raise NotImplementedError  # pragma: no cover

    @property
    def todos(self) -> List[Todo]:
        return [todo for group in self.todo_groups for todo in group.todos]

    @property
    def total_todos(self) -> int:
        return len(self.todos)

    # A fixed project has no siblings to be shifted among, and nothing about it
    # is stored, so the whole editing side of a model is a no-op here
    def is_first_sibling(self) -> bool:
        return True

    def is_last_sibling(self) -> bool:
        return True

    @property
    def siblings(self) -> List["FixedProject"]:
        return [self]


# How todos are ordered where the point is when they were finished: the most
# recently completed first. A todo ticked off before there was anywhere to
# write the date down has none, and sorts below everything that has one
def completion_key(todo: Todo) -> datetime:
    return todo.completed_at or datetime.min


# The same, for the Bin: the thing thrown away last is the thing most likely
# to be wanted back, so it sits at the top
def binned_key(todo: Todo) -> datetime:
    return todo.binned_at or datetime.min


def binned_tasks() -> List[Todo]:
    """
    The tasks in the Bin: the binned todos nothing binned is filed under

    Throwing a todo away throws away everything under it, so a step whose task
    went in the Bin belongs inside that task rather than beside it. A step
    binned on its own has no binned todo above it and stands as a task of its
    own, which is exactly what it is.

    One task is one row of the pane, and one thing to put back or be rid of,
    so it is what both the Bin and the key that empties it count in.
    """

    query = select(Todo).where(Todo.binned_at.is_not(None))
    todos = manager.session.execute(query).scalars().all()

    return [
        todo
        for todo in todos
        if todo.parent_todo is None or not todo.parent_todo.is_binned
    ]


def _day_heading(day: date) -> str:
    """
    What opens a day's block: the day itself, or a name for the nearest two

    The days plans are made against get named rather than dated, the same way
    the date columns say "Today" instead of writing it out.
    """

    if day == date.today():
        return "Today"

    if day == date.today() + timedelta(days=1):
        return "Tomorrow"

    return day_label(day)


class TodayProject(FixedProject):
    """
    Everything scheduled for today, wherever in the tree it is filed

    What the day view adds is a block per project, so a row can still be
    placed at a glance; what it drops is the day itself, which every row here
    shares with the pane it is sitting in.

    A row is a whole task: scheduling a task puts its steps on the day with
    it, drawn underneath it the way its own project draws them, whatever
    dates they carry themselves. Scheduling a single step of an unscheduled
    task puts that step here on its own, since that step is all the day was
    asked for.

    Work planned for a day already gone by is here too, at the top of the
    block it belongs to and marked as having slipped. A plan nobody got to is
    not finished with the moment its day runs out — it is today's problem,
    and the day it was missed on is the last place it would be found in.
    """

    key = "today"
    title = "Today"
    icon = "󰃭"

    # Every task in here is scheduled for today or earlier, and the steps
    # under one are read against the task rather than against the pane, so the
    # column would say "Today" nearly the whole way down. The day a row that
    # slipped was planned for is on the row itself instead
    hidden_columns = ("scheduled",)

    marks_overscheduled = True

    @staticmethod
    def _scheduled_by_today() -> List[Todo]:
        """
        Everything planned for today or for a day that has already gone by
        """

        end = datetime.combine(date.today(), time.min) + timedelta(days=1)
        query = select(Todo).where(
            Todo.pending == True,
            Todo.binned_at.is_(None),
            Todo.scheduled < end,
        )

        return task_roots(list(manager.session.execute(query).scalars().all()))

    @property
    def todo_groups(self) -> List[TodoGroup]:
        groups: Dict[int, List[Todo]] = {}
        projects: Dict[int, Project] = {}

        for todo in self._scheduled_by_today():
            project = owning_project(todo)

            # A todo hanging off nothing has no block to go in
            if project is None:  # pragma: no cover
                continue

            projects[project.id] = project
            groups.setdefault(project.id, []).append(todo)

        order = _project_order()

        return [
            scheduled_group(
                groups[project_id],
                label=project_path(projects[project_id]),
            )
            for project_id in sorted(groups, key=lambda i: order.get(i, 0))
        ]


class UpcomingProject(FixedProject):
    """
    Everything scheduled from today on, a block per day

    Where Today opens a block per project, this one is grouped by the day the
    work is planned for, nearest day first, so the week ahead reads top to
    bottom. Today opens it rather than being left to the project above: this
    is the pane work is moved around in, and a day that cannot be seen is a
    day nothing can be moved off or onto.

    The project a row is filed under is no longer in the heading here, so the
    rows carry it themselves. A row is a whole task, the same way it is in
    Today: the steps of a scheduled task come along with it.

    Nothing is grouped under a day that has gone by. Work planned for one is
    drawn at the top of today's block, marked as having slipped: a day in the
    past is a day nothing can be done on, and the pane exists to move that
    work onto a day something can.
    """

    key = "upcoming"
    title = "Upcoming"
    # The calendar and clock the date columns mark a date still to come with,
    # so the project and the dates under it say the same thing
    icon = "󰃰"

    show_owning_project = True

    # Every row under a heading is scheduled for the day it names — bar the
    # ones that slipped into today, which say the day they were planned for
    # themselves — so the column would say the same thing over and over
    hidden_columns = ("scheduled",)

    # The deadline is read against those headings, and a day either side of it
    # is what matters there rather than the hour
    day_only_columns = ("due",)

    marks_overscheduled = True

    @staticmethod
    def _scheduled() -> List[Todo]:
        query = select(Todo).where(
            Todo.pending == True,
            Todo.binned_at.is_(None),
            Todo.scheduled.is_not(None),
        )

        # Cut down across the whole pane rather than a day at a time: a step
        # planned for a different day than the task it belongs to is drawn
        # inside that task, in the task's own block, and a pane draws no todo
        # twice. The two of them can only be that far apart in work planned
        # before a day meant the whole of a task
        return task_roots(list(manager.session.execute(query).scalars().all()))

    @property
    def todo_groups(self) -> List[TodoGroup]:
        groups: Dict[date, List[Todo]] = {}
        today = date.today()

        for todo in self._scheduled():
            assert todo.scheduled is not None

            # A day that has gone by is no day to plan against, so what was
            # left on one is carried into today rather than opening a block
            # behind the pane that nothing can be moved onto
            day = max(todo.scheduled.date(), today)
            groups.setdefault(day, []).append(todo)

        # A block at a time, each gathering only what falls on its own day:
        # a task whose steps are spread over the week is drawn for context in
        # every day it has work in, with that day's steps alone under it
        return [
            scheduled_group(groups[day], label=_day_heading(day))
            for day in sorted(groups)
        ]


class CompletedProject(FixedProject):
    """
    Every finished task, wherever in the tree it is filed

    Finishing a task moves it in here: it leaves the pane of the project it
    belongs to and turns up in this one, which is one run of rows, the most
    recently finished at the top, so the pane reads as a log of what has been
    getting done. Nothing groups it: a log is read from the top down, and the
    project a row came out of trails the row itself the way it does in
    Upcoming.

    A task made of steps arrives whole, with its steps under it: it is
    finished when the last of them is, and until then it stays in its own
    project with the ones already done still shown under it.

    Unticking a row — the task or any step of it — hands the whole of it back
    to the project it came from: the todo was never moved in the database,
    only shown here while it was done with.
    """

    key = "completed"
    title = "Completed"
    # The ticked checkbox the rows themselves are marked with, so the project
    # says the same thing its contents do
    icon = "󰄵"

    pinned_bottom = True
    muted = True

    # Nothing here says which project a row came out of, so the rows do
    show_owning_project = True

    # A row unticked in here is on its way back to its own project, and what
    # sends it there is typed into the row: it stays put until that is done
    holds_unticked_rows = True

    # Nothing in here is planned or owed any more; what is worth knowing is
    # when it was finished, which takes the place of both date columns. They
    # can still be edited from the bar, which is what lets a todo be dated
    # again on its way back out
    hidden_columns = ("scheduled", "due")
    extra_columns = ("completed",)

    # The log is read a day at a time: what was finished today says "Today"
    # whatever the hour, so the hour only ever shows up on the older rows,
    # where it is least worth the width it takes from the descriptions
    day_only_columns = ("completed",)

    @staticmethod
    def _completed() -> List[Todo]:
        """
        The finished tasks: the completed todos filed straight under a project

        What comes in here is a whole task rather than a step of one. A todo
        that hangs off another is part of the task above it: ticking it off
        leaves it where it is, under a parent that is still being worked on,
        and it only arrives here inside that parent, once the last of its
        siblings has been done too. It is drawn under it here the way it was
        drawn under it there, and goes back out with it.
        """

        query = select(Todo).where(
            Todo.pending == False,
            Todo.binned_at.is_(None),
            Todo.parent_todo_id.is_(None),
        )

        return list(manager.session.execute(query).scalars().all())

    @property
    def todo_groups(self) -> List[TodoGroup]:
        todos = sorted(self._completed(), key=completion_key, reverse=True)

        # One block, and no heading over it: what the rows have in common is
        # that they are done, which the pane has already said
        return [TodoGroup(todos=todos)]


class BinProject(FixedProject):
    """
    Everything that has been thrown away and not yet emptied out

    The other side of the Completed project, and drawn the same way: one run
    of rows with the most recent at the top, each carrying the project it came
    out of and the date it landed here instead of the dates it was working to.
    Where Completed is a log of what got done, this is a log of what got
    dropped — and unlike Completed, it can be undone: a row restored from here
    goes straight back to the project it was filed under.

    A task arrives whole, with its steps under it, and goes back out whole.
    What it does not do is leave on its own: a todo stays in the Bin until it
    is either restored or deleted for good, which is what makes throwing
    something away a decision that can be slept on.
    """

    key = "bin"
    title = "Bin"
    # The waste basket, so the project says the same thing about its rows that
    # the key which fills it does
    icon = "󰆴"

    pinned_bottom = True
    muted = True

    gathers_binned = True

    # Nothing here says which project a row came out of, so the rows do
    show_owning_project = True

    # Nothing in the Bin is planned or owed any more; what is worth knowing is
    # when it was thrown away, which is how long there is left to change your
    # mind. It takes the place of both date columns, which can still be edited
    # from the bar on a row that is on its way back out
    hidden_columns = ("scheduled", "due")
    extra_columns = ("binned",)

    # Read a day at a time, the way the completion log is: what went in today
    # says "Today" whatever the hour
    day_only_columns = ("binned",)

    @property
    def todo_groups(self) -> List[TodoGroup]:
        todos = sorted(binned_tasks(), key=binned_key, reverse=True)

        # One block, and no heading over it: what the rows have in common is
        # that they were thrown out, which the pane has already said
        return [TodoGroup(todos=todos)]


_FIXED_PROJECTS: List[FixedProject] = []


def register_fixed_project(project: FixedProject) -> FixedProject:
    """
    Puts a fixed project in the pane, under the ones already registered
    """

    _FIXED_PROJECTS.append(project)
    return project


def fixed_projects() -> List[FixedProject]:
    return list(_FIXED_PROJECTS)


def fixed_project_from_key(key: str) -> Optional[FixedProject]:
    for project in _FIXED_PROJECTS:
        if project.key == key:
            return project

    return None


def fixed_project_from_id(_id: str) -> Optional[FixedProject]:
    """
    The fixed project a row id belongs to, or None if the row is a stored one
    """

    if not _id.startswith(f"{FIXED_ID_PREFIX}_"):
        return None

    return fixed_project_from_key(_id[len(FIXED_ID_PREFIX) + 1 :])


TODAY = TodayProject()
register_fixed_project(TODAY)

UPCOMING = UpcomingProject()
register_fixed_project(UPCOMING)

COMPLETED = CompletedProject()
register_fixed_project(COMPLETED)

# Right under Completed, at the very foot of the pane: the two places work
# leaves the tree for, in the order they are looked in
BIN = BinProject()
register_fixed_project(BIN)
