from dataclasses import dataclass
from typing import List, Optional, Union

from sqlalchemy import ForeignKey, select
from sqlalchemy.orm import Mapped, mapped_column, relationship

from ..api.todo import Todo
from .manager import manager
from .model import TodooitModel

ModelType = Union["Project", "Todo"]


@dataclass
class LevelChange:
    """
    What moving a project to another level meant

    Falsy when there is nothing worth telling the status bar.
    """

    project: "Project"
    # Took its new parent's color in place of its own
    recolored: bool = False

    def __bool__(self) -> bool:
        return self.recolored

    def summary(self) -> str:
        return "recolored to match its new parent" if self.recolored else ""


class Project(TodooitModel[LevelChange]):
    description: Mapped[str] = mapped_column(default="")
    is_root: Mapped[bool] = mapped_column(default=False)

    # Palette slot (not the color itself), so it survives theme changes
    color: Mapped[Optional[int]] = mapped_column(default=None)

    parent_project_id: Mapped[Optional[int]] = mapped_column(
        ForeignKey("project.id"), default=None, index=True
    )
    parent_project: Mapped[Optional["Project"]] = relationship(
        "Project",
        back_populates="projects",
        remote_side="Project.id",
    )

    projects: Mapped[List["Project"]] = relationship(
        "Project",
        back_populates="parent_project",
        cascade="all",
        order_by="Project.order_index",
    )
    # No delete-orphan: todos lifted out of a binned project must survive
    todos: Mapped[List["Todo"]] = relationship(
        "Todo",
        back_populates="parent_project",
        cascade="all",
        order_by="Todo.order_index",
    )

    @classmethod
    def _get_or_create_root(cls) -> "Project":
        query = select(Project).where(Project.is_root == True)
        root = manager.session.execute(query).scalars().first()

        if root is None:
            root = Project(is_root=True)

        return root

    @classmethod
    def from_id(cls, _id: str) -> "Project":
        _id = _id.removeprefix("Project_")
        query = select(Project).where(Project.id == _id)
        res = manager.session.execute(query).scalars().first()
        assert res is not None
        return res

    @property
    def parent(self) -> Optional["Project"]:
        return self.parent_project

    @property
    def total_todos(self) -> int:
        """
        Pending, unbinned todos in here and in all sub projects, at every depth
        """

        return sum(project.total_todos for project in self.projects) + sum(
            1 + todo.total_children
            for todo in self.todos
            if todo.pending and not todo.is_binned
        )

    @property
    def total_projects(self) -> int:
        return len(self.descendants)

    @property
    def siblings(self) -> List["Project"]:
        if not self.parent_project:
            return []

        assert not self.is_root

        return self.parent_project.projects

    @property
    def color_root(self) -> "Project":
        """
        The top-level project whose color this whole tree uses
        """

        project = self

        while project.parent_project is not None and not project.parent_project.is_root:
            project = project.parent_project

        return project

    @property
    def descendants(self) -> List["Project"]:
        """
        Every project nested under this one, at every depth
        """

        found: List["Project"] = []

        for child in self.projects:
            found.append(child)
            found += child.descendants

        return found

    def set_color(self, color: Optional[int]) -> None:
        """
        Set (or clear, with None) the color of the whole tree this project is in
        """

        top = self.color_root

        for project in [top, *top.descendants]:
            project.color = color

        # The sub projects are already in the session, so one save commits all
        top.save()

    def add_project(self) -> "Project":
        project = Project(parent_project=self)
        project.save()
        return project

    def add_todo(self) -> "Todo":
        todo = Todo(parent_project=self)
        todo.save()
        return todo

    def add_sibling(self) -> "Project":
        project = Project(
            parent_project=self.parent_project,
            order_index=self.order_index + 1,
        )
        project.save()
        return project

    @property
    def _children_of_kind(self) -> List["Project"]:
        return self.projects

    @property
    def _parent_of_kind(self) -> Optional["Project"]:
        parent = self.parent_project
        return None if parent is None or parent.is_root else parent

    def _place(self, parent: TodooitModel) -> LevelChange:
        """
        Under another project the whole tree takes that project's color;
        back at the top level it keeps the one it had
        """

        assert isinstance(parent, Project)

        before = self.color
        self.parent_project = parent

        # Saving colors this project itself; the ones under it follow here
        if not parent.is_root:
            for project in self.descendants:
                project.color = parent.color

        self.save()
        return LevelChange(self, recolored=self.color != before)

    def save(self) -> None:
        # Sub projects always inherit their parent's color. no_autoflush keeps
        # the (possibly expired) parent's reload from flushing this half-built row
        parent = self.parent_project

        with self.session.no_autoflush:
            if parent is not None and not parent.is_root:
                self.color = parent.color

        if not parent and not self.is_root:
            self.parent_project = self._get_or_create_root()

        return super().save()

    @classmethod
    def all(cls) -> List["Project"]:
        query = select(Project).where(Project.is_root == False)
        return list(manager.session.execute(query).scalars().all())
