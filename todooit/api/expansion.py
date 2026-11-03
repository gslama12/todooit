"""
Expansion state by row id, for the panes that know a row only by its uuid

The state itself is `TodooitModel.expanded`. Ids that are no stored row
(fixed projects, headings) are always open and ignore being closed.
"""

from typing import Optional, Union

from .project import Project
from .todo import Todo


def _model(_id: str) -> Optional[Union[Project, Todo]]:
    if _id.startswith("Todo_"):
        return Todo.from_id(_id)

    if _id.startswith("Project_"):
        return Project.from_id(_id)

    return None


def is_expanded(_id: str) -> bool:
    model = _model(_id)
    return True if model is None else model.expanded


def set_expanded(_id: str, expanded: bool) -> None:
    model = _model(_id)

    if model is not None:
        model.set_expanded(expanded)
