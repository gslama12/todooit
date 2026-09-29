from typing import TYPE_CHECKING, Dict, Generic, TypeVar
from todooit.api import Project, Todo, fixed_project_from_id
from todooit.ui.widgets.renderers import (
    BaseRenderer,
    TodoRender,
    ProjectRender,
)

T = TypeVar("T", bound=BaseRenderer)

if TYPE_CHECKING:  # pragma: no cover
    from .model_tree import ModelTree


class RenderDict(Dict, Generic[T]):
    """
    Default Dict implementation for Todo/Project Renderers
    """

    def __init__(self, tree: "ModelTree"):
        super().__init__()
        self.tree = tree

    def from_id(self, _id: str) -> T:
        raise NotImplementedError  # pragma: no cover

    def __getitem__(self, __key: str) -> T:
        return super().__getitem__(__key)

    def __missing__(self, key: str) -> T:
        self[key] = self.from_id(key)
        return self[key]


class ProjectRenderDict(RenderDict[ProjectRender]):
    """
    Default Dict implementation for Project Renderers
    """

    def from_id(self, _id: str) -> ProjectRender:
        # Fixed projects aren't in the database; check the registry first
        project = fixed_project_from_id(_id) or Project.from_id(_id)
        return ProjectRender(project, self.tree)


class TodoRenderDict(RenderDict[TodoRender]):
    """
    Default Dict implementation for Todo Renderers
    """

    def from_id(self, _id: str) -> TodoRender:
        t = Todo.from_id(_id)
        return TodoRender(t, self.tree)
