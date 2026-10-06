"""
The Bin: throwing work away and getting it back

Dropping a todo moves it (with its children) to the Bin until it is restored
or the Bin is emptied. Dropping a project deletes only the project row: its
todos go to the Bin carrying their `origin_path`, which is used to rebuild the
project if one of them is restored later.
"""

from datetime import datetime
from typing import List, Optional

from .fixed_projects import binned_tasks, project_path, split_path
from .manager import manager
from .placement import bin_row_of
from .project import Project
from .todo import Todo

# Name prefix for a project rebuilt to hold a restored todo
REVIVED_PREFIX = "revived - "

# Fallback project name when a todo has no origin path
UNKNOWN_PROJECT = "recovered"


def move_todo_to_bin(todo: Todo) -> None:
    """
    Bin a todo and all its descendants under one shared timestamp
    """

    stamp = datetime.now()

    for node in todo.family:
        node.binned_at = stamp

    todo.save()


def restore_todo(todo: Todo) -> List[Project]:
    """
    Restore a binned todo's whole task; returns any projects that had to be rebuilt

    Completed tasks stay orphaned (they live in the Completed log) until unticked.
    """

    todo = bin_row_of(todo)

    for node in todo.family:
        node.binned_at = None

    todo.save()

    if todo.pending:
        return revive_home(todo)

    return []


def revive_home(todo: Todo) -> List[Project]:
    """
    Put an orphaned todo back into the project named by its origin path

    Missing projects along the path are recreated with `REVIVED_PREFIX`;
    returns the ones created.
    """

    if not todo.is_orphan:
        return []

    created: List[Project] = []
    project = _project_from_path(todo.origin_path, created)

    todo.order_index = len(project.todos)
    todo.parent_project = project
    todo.origin_path = ""
    todo.save()

    return created


def _project_from_path(path: str, created: List[Project]) -> Project:
    """
    The project a path names, creating whatever part of it is missing
    """

    names = split_path(path)
    parent = Project._get_or_create_root()

    for name in names or [UNKNOWN_PROJECT]:
        child = _child_named(parent, name)

        if child is None:
            child = Project(
                parent_project=parent,
                order_index=len(parent.projects),
            )
            child.description = f"{REVIVED_PREFIX}{name}"
            child.save()
            created.append(child)

        parent = child

    return parent


def _child_named(parent: Project, name: str) -> Optional[Project]:
    """
    The child project called `name` (or its revived version), if any
    """

    for child in parent.projects:
        if child.description in (name, f"{REVIVED_PREFIX}{name}"):
            return child

    return None


def move_project_to_bin(project: Project) -> None:
    """
    Delete a project, moving all todos in it and its sub projects to the Bin
    """

    stamp = datetime.now()

    for node in [project, *project.descendants]:
        path = project_path(node)

        for todo in list(node.todos):
            todo.origin_path = path
            todo.parent_project = None

            for member in todo.family:
                member.binned_at = stamp

            manager.session.add(todo)

    manager.commit()
    project.drop()


def empty_bin() -> List[str]:
    """
    Permanently delete everything in the Bin; returns the uuids of all deleted rows
    """

    tasks = binned_tasks()
    gone = [node.uuid for todo in tasks for node in todo.family]

    # Deleting the task cascades to its children
    for todo in tasks:
        manager.session.delete(todo)

    manager.commit()

    return gone
