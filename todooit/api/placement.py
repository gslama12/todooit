"""
Placement: where a todo lives

A todo's home is the one pane it lives in: its project or the Bin. A
completed todo stays home in its project, hidden until shown. Day panes
(Today, Upcoming) gather todos but are never their home. This is the only
module that decides a todo's home.

An orphan is always binned: every todo that isn't in the Bin has a project.
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
    The pane a todo lives in: the Bin if it is binned, even a step whose
    parent is not, else its project. None only for a todo not placed yet, since an
    orphan is always binned.
    """

    # Imported here: fixed_projects imports this module
    from .fixed_projects import BIN

    if todo.is_binned:
        return BIN

    return project_of(todo)
