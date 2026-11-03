"""
Built-in projects (Today, Upcoming, Completed, Bin) that aren't stored in the DB

A fixed project can't be created, renamed, moved or deleted and owns no todos;
its contents are gathered from the real projects on every read. It mimics the
parts of `Project` the trees and bar read, told apart by `is_fixed`.

To add one: subclass `FixedProject` (key, title, icon, `todo_groups`) and add
an instance to `_FIXED_PROJECTS` at the bottom.
"""

from dataclasses import dataclass, field
from datetime import date, datetime, time, timedelta
from typing import Dict, List, Optional, Tuple

from sqlalchemy import select

from ..utils.day_names import day_label
from .manager import manager
from .placement import completed_row_of, project_of
from .project import Project
from .todo import Todo, priority_key

FIXED_ID_PREFIX = "FixedProject"

# Between the steps of a project path, written the way it is typed (`work/api`)
PATH_SEPARATOR = "/"

# What paths were written with before; Bin entries from back then still carry it
LEGACY_PATH_SEPARATOR = " › "


@dataclass
class TodoRow:
    """
    One row of a block

    `under` is None for a row that draws its own steps, as its project would.
    A day pane's rows pick what hangs off them instead: `under` then holds
    exactly the rows to draw beneath it. A context row is an ancestor drawn
    only to show where the rows under it belong; it isn't that block's work.
    """

    todo: Todo
    under: Optional[List["TodoRow"]] = None
    is_context: bool = False


@dataclass
class TodoGroup:
    """
    A block of todos under one heading (a blank label means no heading)

    `todos` is what was gathered, `rows` how it is drawn (flat unless context
    rows are needed).
    """

    todos: List[Todo]
    label: str = ""
    rows: List[TodoRow] = field(default_factory=list)

    def __post_init__(self) -> None:
        if not self.rows:
            self.rows = [TodoRow(todo) for todo in self.todos]


def _day_rows(gathered: List[Todo]) -> List[TodoRow]:
    """
    A day block's rows: every gathered todo under its full family line

    An ancestor gathered in the same block is a regular row, any other one a
    context row. Each row draws only the rows picked for it here, never its
    own steps, so a step planned for another day stays on that day. An
    ancestor shared by several gathered todos is drawn once, at the position
    of the first one.
    """

    work = {todo.id for todo in gathered}
    rows: Dict[int, TodoRow] = {}
    tops: List[TodoRow] = []

    def row_for(todo: Todo) -> TodoRow:
        row = rows.get(todo.id)

        if row is not None:
            return row

        row = TodoRow(todo, under=[], is_context=todo.id not in work)
        rows[todo.id] = row

        parent = todo.parent_todo

        if parent is None:
            tops.append(row)
        else:
            under = row_for(parent).under
            assert under is not None
            under.append(row)

        return row

    for todo in gathered:
        row_for(todo)

    return tops


# Overscheduled work first, then by priority
def slipped_first(todo: Todo) -> tuple:
    return (not todo.is_overscheduled,) + priority_key(todo)


def scheduled_group(todos: List[Todo], label: str = "") -> TodoGroup:
    """
    A block of the work planned for one day, most pressing first
    """

    gathered = sorted(todos, key=slipped_first)

    return TodoGroup(
        todos=gathered,
        label=label,
        rows=_day_rows(gathered),
    )


def _scheduled(before: Optional[datetime] = None) -> List[Todo]:
    """
    Pending, unbinned, scheduled todos, optionally only those before `before`

    Every step counts on its own day, whatever day its parent is planned for.
    """

    query = select(Todo).where(
        Todo.pending == True,
        Todo.binned_at.is_(None),
        Todo.scheduled.is_not(None) if before is None else Todo.scheduled < before,
    )

    return list(manager.session.execute(query).scalars().all())


def project_path(project: Project) -> str:
    """
    The project's name prefixed by its ancestors' names
    """

    parts = []
    node: Optional[Project] = project

    while node is not None and not node.is_root:
        parts.append(node.description)
        node = node.parent_project

    return PATH_SEPARATOR.join(reversed(parts))


def split_path(path: str) -> List[str]:
    """
    The names in a stored project path, whichever separator it was written with
    """

    path = path.replace(LEGACY_PATH_SEPARATOR, PATH_SEPARATOR)

    return [name.strip() for name in path.split(PATH_SEPARATOR) if name.strip()]


def _project_order() -> Dict[int, int]:
    """
    Each project's position in the tree read top to bottom
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
    icon: str = ""

    is_fixed: bool = True

    # Pinned to the bottom of the projects pane
    pinned_bottom: bool = False

    # Drawn in gray instead of the accent color
    muted: bool = False

    # Rows show which project they come from
    show_owning_project: bool = False

    # Columns hidden because the headings already say them (still editable via the bar)
    hidden_columns: Tuple[str, ...] = ()

    # Columns added right after the description
    extra_columns: Tuple[str, ...] = ()

    # Date columns shown as a day without the time
    day_only_columns: Tuple[str, ...] = ()

    # After unticking a row here, jump to its home project
    sends_unticked_home: bool = False

    # Shows binned todos (every other pane hides them)
    gathers_binned: bool = False

    # Marks rows scheduled for a past day
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

    # Nothing to reorder: a fixed project is its own only sibling
    def is_first_sibling(self) -> bool:
        return True

    def is_last_sibling(self) -> bool:
        return True

    @property
    def siblings(self) -> List["FixedProject"]:
        return [self]


def binned_tasks() -> List[Todo]:
    """
    Binned todos whose parent isn't binned too (one row per binned task)
    """

    query = select(Todo).where(Todo.binned_at.is_not(None))
    todos = manager.session.execute(query).scalars().all()

    return [
        todo
        for todo in todos
        if todo.parent_todo is None or not todo.parent_todo.is_binned
    ]


def _day_heading(day: date) -> str:
    if day == date.today():
        return "Today"

    if day == date.today() + timedelta(days=1):
        return "Tomorrow"

    return day_label(day)


class TodayProject(FixedProject):
    """
    Everything scheduled for today or earlier, one block per project

    A task shows only its steps planned for today, or alone if there are
    none. A step sits under its full family line: an ancestor that is itself
    today's work (planned today or slipped) is a regular row, an unscheduled
    one a context row. Overscheduled work sits at the top of its block.
    """

    key = "today"
    title = "Today"
    icon = "󰃭"

    hidden_columns = ("scheduled",)

    marks_overscheduled = True

    @property
    def todo_groups(self) -> List[TodoGroup]:
        end = datetime.combine(date.today(), time.min) + timedelta(days=1)
        groups: Dict[int, List[Todo]] = {}
        projects: Dict[int, Project] = {}

        for todo in _scheduled(before=end):
            project = project_of(todo)

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
    Everything scheduled, one block per day starting today

    Work scheduled for a past day is shown in today's block, marked as
    overscheduled. A step planned for a later day than its task is listed on
    its own day, under its ancestors as context rows; a task whose steps fall
    on several days is context on each of them.
    """

    key = "upcoming"
    title = "Upcoming"
    icon = "󰃰"

    show_owning_project = True
    hidden_columns = ("scheduled",)
    day_only_columns = ("due",)
    marks_overscheduled = True

    @property
    def todo_groups(self) -> List[TodoGroup]:
        groups: Dict[date, List[Todo]] = {}
        today = date.today()

        for todo in _scheduled():
            assert todo.scheduled is not None

            day = max(todo.scheduled.date(), today)
            groups.setdefault(day, []).append(todo)

        return [
            scheduled_group(groups[day], label=_day_heading(day))
            for day in sorted(groups)
        ]


class CompletedProject(FixedProject):
    """
    Log of completed todos, most recently finished first

    A step finished under an open parent is a row of its own, like any task;
    a completed parent carries its steps under it. Unticking a row sends it
    back to its project, reopening whatever it is nested under.
    """

    key = "completed"
    title = "Completed"
    icon = "󰄵"

    pinned_bottom = True
    muted = True
    show_owning_project = True
    sends_unticked_home = True
    hidden_columns = ("scheduled", "due")
    extra_columns = ("completed",)
    day_only_columns = ("completed",)

    @property
    def todo_groups(self) -> List[TodoGroup]:
        query = select(Todo).where(
            Todo.pending == False,
            Todo.binned_at.is_(None),
        )
        rows = [
            todo
            for todo in manager.session.execute(query).scalars().all()
            if completed_row_of(todo) is todo
        ]
        todos = sorted(
            rows,
            key=lambda todo: todo.completed_at or datetime.min,
            reverse=True,
        )

        return [TodoGroup(todos=todos)]


class BinProject(FixedProject):
    """
    Binned tasks, most recently binned first, until restored or emptied
    """

    key = "bin"
    title = "Bin"
    icon = "󰆴"

    pinned_bottom = True
    muted = True
    gathers_binned = True
    show_owning_project = True
    hidden_columns = ("scheduled", "due")
    extra_columns = ("binned",)
    day_only_columns = ("binned",)

    @property
    def todo_groups(self) -> List[TodoGroup]:
        todos = sorted(
            binned_tasks(),
            key=lambda todo: todo.binned_at or datetime.min,
            reverse=True,
        )

        return [TodoGroup(todos=todos)]


TODAY = TodayProject()
UPCOMING = UpcomingProject()
COMPLETED = CompletedProject()
BIN = BinProject()

# In pane order
_FIXED_PROJECTS: List[FixedProject] = [TODAY, UPCOMING, COMPLETED, BIN]


def fixed_projects() -> List[FixedProject]:
    return list(_FIXED_PROJECTS)


def fixed_project_from_key(key: str) -> Optional[FixedProject]:
    for project in _FIXED_PROJECTS:
        if project.key == key:
            return project

    return None


def fixed_project_from_id(_id: str) -> Optional[FixedProject]:
    """
    The fixed project a row id belongs to, or None for a stored project
    """

    if not _id.startswith(f"{FIXED_ID_PREFIX}_"):
        return None

    return fixed_project_from_key(_id.removeprefix(f"{FIXED_ID_PREFIX}_"))
