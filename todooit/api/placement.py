"""
Placement: where a todo lives

A todo's home is the one pane it lives in: its project, Completed or the Bin.
Day panes (Today, Upcoming) gather todos but are never their home. This is
the only module that decides a todo's home.
"""

from typing import TYPE_CHECKING, Optional, Union

from .project import Project
from .todo import Todo

if TYPE_CHECKING:  # pragma: no cover
    from .fixed_projects import FixedProject

Home = Union[Project, "FixedProject"]


def root_of(todo: Todo) -> Todo:
    """
    The todo at the top of a todo's family: itself, unless it is a step
    """

    return (todo.ancestors or [todo])[-1]


def project_of(todo: Todo) -> Optional[Project]:
    """
    The project a todo is filed under, however deeply nested; None for an orphan
    """

    return root_of(todo).parent_project


def bin_row_of(todo: Todo) -> Todo:
    """
    The row the Bin draws a binned todo in: the highest binned todo in its line
    """

    row = todo

    for ancestor in todo.ancestors:
        if not ancestor.is_binned:
            break

        row = ancestor

    return row


def home_of(todo: Todo) -> Optional[Home]:
    """
    The pane a todo lives in, as a project a screen can open directly

    The Bin for a binned todo, even a step whose parent is not binned; else
    Completed if its root is completed, steps included; else its project, so
    a completed step under an open root stays in place. None only for an open
    orphan, which never outlives the call that reopened it: reopening or
    restoring one rebuilds its project from its origin path.
    """

    # Imported here: fixed_projects imports this module
    from .fixed_projects import BIN, COMPLETED

    if todo.is_binned:
        return BIN

    if root_of(todo).is_completed:
        return COMPLETED

    return project_of(todo)
