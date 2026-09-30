from .model import TodooitModel, BaseModel
from .todo import (
    SORT_KEYS,
    Todo,
    TodoSortModeType,
    freeze_sort_order,
    sort_todos,
)
from .project import Project
from .pinned_note import PINNED_NOTE_ID, PinnedNote
from .fixed_projects import (
    FixedProject,
    TodoGroup,
    TodoRow,
    TODAY,
    UPCOMING,
    COMPLETED,
    BIN,
    fixed_project_from_id,
    fixed_project_from_key,
    fixed_projects,
    binned_tasks,
)
from .recycle import (
    REVIVED_PREFIX,
    empty_bin,
    move_project_to_bin,
    move_todo_to_bin,
    restore_todo,
    revive_home,
)
from .history import ChangedRows, History
from . import lifecycle
from .manager import manager
from .hooks import fix_hooks, validation_hooks


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
