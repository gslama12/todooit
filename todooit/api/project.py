from typing import List, Optional, Union
from sqlalchemy import ForeignKey, select
from sqlalchemy.orm import Mapped, mapped_column, relationship
from ..api.todo import Todo
from .model import DooitModel
from .manager import manager

ModelType = Union["Project", "Todo"]


class Project(DooitModel):
    id: Mapped[int] = mapped_column(primary_key=True, autoincrement=True)
    order_index: Mapped[int] = mapped_column(default=-1)
    description: Mapped[str] = mapped_column(default="")
    is_root: Mapped[bool] = mapped_column(default=False)

    # Which slot of the project palette this one is drawn in, or None for a
    # project that was never given one. The slot is stored rather than the
    # color itself, so a project keeps its place in the palette when the theme
    # underneath it changes.
    color: Mapped[Optional[int]] = mapped_column(default=None)

    # --------------------------------------------------------------
    # ------------------- Relationships ----------------------------
    # --------------------------------------------------------------

    parent_project_id: Mapped[Optional[int]] = mapped_column(
        ForeignKey("project.id"), default=None, index=True
    )
    parent_project: Mapped[Optional["Project"]] = relationship(
        "Project",
        back_populates="projects",
        remote_side=[id],
    )

    projects: Mapped[List["Project"]] = relationship(
        "Project",
        back_populates="parent_project",
        cascade="all",
        order_by="Project.order_index",
    )
    # Deleting the project still takes its todos with it, but a todo lifted
    # out of it is not thereby deleted: that is how a project is thrown away
    # while what was filed in it goes to the Bin instead of going with it
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
        _id = _id.lstrip("Project_")
        query = select(Project).where(Project.id == _id)
        res = manager.session.execute(query).scalars().first()
        assert res is not None
        return res

    @property
    def parent(self) -> Optional["Project"]:
        return self.parent_project

    @property
    def has_same_parent_kind(self) -> bool:
        return self.parent is not None

    @property
    def total_todos(self) -> int:
        """
        Every todo still to be done in here, counted at every level.

        Sub projects are walked into but never counted themselves: the number
        says how much work sits in here, not how it is filed away. A completed
        todo has moved to the Completed project and is counted there, so what
        is left is what the project's own pane shows, and what it shows leaves
        out whatever has been thrown in the Bin.
        """

        return sum(project.total_todos for project in self.projects) + sum(
            1 + todo.total_children
            for todo in self.todos
            if todo.pending and not todo.is_binned
        )

    @property
    def total_projects(self) -> int:
        """
        Every project nested under this one, counted at every level
        """

        return sum(1 + project.total_projects for project in self.projects)

    @property
    def siblings(self) -> List["Project"]:
        if not self.parent_project:
            return []

        assert not self.is_root

        return self.parent_project.projects

    @property
    def color_root(self) -> "Project":
        """
        The project this one takes its color from

        A color labels a whole tree rather than a single row, so it is held by
        the project at the top of that tree and handed down from there. For a
        top level project that is the project itself.
        """

        project = self

        while project.parent_project is not None and not project.parent_project.is_root:
            project = project.parent_project

        return project

    @property
    def descendants(self) -> List["Project"]:
        """
        Every project filed under this one, at every depth
        """

        found: List["Project"] = []

        for child in self.projects:
            found.append(child)
            found += child.descendants

        return found

    def set_color(self, color: Optional[int]) -> None:
        """
        Put the whole project tree in a palette slot, or take it back out

        The slot belongs to the tree rather than to the row it was typed over:
        it is written to the project at the top of the tree and handed down to
        everything filed under it, so a sub project is never a different color
        from the project it sits in. Clearing works the same way round, which
        is why `None` empties the tree and not just the one row.
        """

        top = self.color_root

        for project in [top, *top.descendants]:
            project.color = color

        # One commit writes the whole tree: the sub projects are already in
        # the session, so saving the top of it puts all of them away together
        top.save()

    def add_project(self) -> "Project":
        project = Project(parent_project=self)
        project.save()
        return project

    def add_todo(self) -> "Todo":
        todo = Todo(parent_project=self)
        todo.save()
        return todo

    def _add_sibling(self) -> "Project":
        project = Project(
            parent_project=self.parent_project,
            order_index=self.order_index + 1,
        )
        project.save()
        return project

    def save(self) -> None:
        # A sub project is always drawn in the color of the project it sits
        # in, so the slot is taken off the parent here rather than being
        # copied at each of the places a project can come into being -- added
        # or built back out of a binned todo's path. Asked before the
        # root is filled in below, since a project that is about to be given
        # the root has no color to take from it anyway, and the root at that
        # point may not be in the session to be asked.
        parent = self.parent_project

        # A parent that the last commit expired is read back from the
        # database here, and the project being saved is not in the session yet
        # for that read to try and flush half of it on the way past
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
