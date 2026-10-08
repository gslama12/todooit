from . import lifecycle
from .cadence import Cadence
from .fixed_projects import (
    BIN,
    COMPLETED,
    TODAY,
    UPCOMING,
    FixedProject,
    TodoGroup,
    TodoRow,
    binned_tasks,
    fixed_project_from_id,
    fixed_project_from_key,
    fixed_projects,
)
from .history import ChangedRows, History
from .hooks import fix_hooks, validation_hooks
from .manager import manager
from .model import BaseModel, TodooitModel
from .pinned_note import PINNED_NOTE_ID, PinnedNote
from .project import Project
from .recycle import (
    REVIVED_PREFIX,
    empty_bin,
    move_project_to_bin,
    move_todo_to_bin,
    restore_todo,
    revive_home,
)
from .todo import (
    SORT_KEYS,
    Todo,
    TodoSortModeType,
    freeze_sort_order,
    sort_todos,
)


def drop_blank_models() -> None:
    """
    Delete childless items with a blank description (left over from quitting mid-edit)
    """

    def is_blank(model) -> bool:
        return not (model.description or "").strip()

    for project in Project.all():
        if is_blank(project) and not project.projects and not project.todos:
            project.drop()

    for todo in Todo.all():
        if is_blank(todo) and not todo.todos:
            todo.drop()


__all__ = [
    "BaseModel",
    "TodooitModel",
    "Cadence",
    "Todo",
    "TodoSortModeType",
    "SORT_KEYS",
    "sort_todos",
    "freeze_sort_order",
    "Project",
    "PinnedNote",
    "PINNED_NOTE_ID",
    "FixedProject",
    "TodoGroup",
    "TodoRow",
    "TODAY",
    "UPCOMING",
    "COMPLETED",
    "BIN",
    "REVIVED_PREFIX",
    "empty_bin",
    "move_project_to_bin",
    "move_todo_to_bin",
    "restore_todo",
    "revive_home",
    "fixed_project_from_id",
    "fixed_project_from_key",
    "fixed_projects",
    "binned_tasks",
    "ChangedRows",
    "History",
    "manager",
    "lifecycle",
    "drop_blank_models",
    "fix_hooks",
    "validation_hooks",
]
