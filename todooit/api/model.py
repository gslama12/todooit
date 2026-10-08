from typing import Any, Generic, List, Optional, TypeVar
from typing_extensions import Protocol, Self
from sqlalchemy.orm import DeclarativeBase, Mapped, mapped_column
from sqlalchemy.ext.declarative import declared_attr
from .manager import manager


class BaseModel(DeclarativeBase):
    pass


class Tellable(Protocol):
    """
    What a change to the tree meant, in words the status bar can show

    Falsy when there is nothing worth telling.
    """

    def __bool__(self) -> bool: ...

    def summary(self) -> str: ...


# What moving an item between levels returns: a todo's lifecycle `Outcome`,
# a project's `LevelChange`
ChangeT = TypeVar("ChangeT", bound=Tellable)


class BaseModelMixin:
    @declared_attr
    def __tablename__(cls):
        return cls.__name__.lower()


class TodooitModel(BaseModel, BaseModelMixin, Generic[ChangeT]):
    """
    Base class for the tree models (projects and todos)
    """

    __abstract__ = True

    id: Mapped[int] = mapped_column(primary_key=True, autoincrement=True)
    order_index: Mapped[int] = mapped_column(default=-1)

    @property
    def uuid(self) -> str:
        return f"{self.__class__.__name__}_{self.id}"

    @property
    def parent(self) -> Any:
        raise NotImplementedError  # pragma: no cover

    @property
    def nest_level(self):
        level = 0
        parent = self.parent

        while (
            parent
            and isinstance(self, parent.__class__)
            and not getattr(parent, "is_root", False)
        ):
            level += 1
            parent = parent.parent

        return level

    @property
    def siblings(self) -> List[Any]:
        raise NotImplementedError  # pragma: no cover

    @classmethod
    def from_id(cls, _id: str) -> Self:
        raise NotImplementedError  # pragma: no cover

    @property
    def session(self):
        return manager.session

    # An item without siblings (e.g. an orphaned todo) counts as both first and last
    def is_last_sibling(self) -> bool:
        siblings = self.siblings
        return not siblings or siblings[-1].id == self.id

    def is_first_sibling(self) -> bool:
        siblings = self.siblings
        return not siblings or siblings[0].id == self.id

    def swap_with(self, other: Self) -> bool:
        """
        Exchange order positions with a sibling

        The run is renumbered first so gaps or duplicate indexes can't make
        the swap a no-op.
        """

        siblings = list(self.siblings)

        if other is self or other not in siblings:
            return False

        for order, model in enumerate(siblings):
            model.order_index = order

        self.order_index, other.order_index = other.order_index, self.order_index

        self.session.add_all(siblings)
        manager.commit()

        return True

    def shift_up(self) -> bool:
        """
        Move one place up in the stored order (not necessarily one row up on screen)
        """

        if self.is_first_sibling():
            return False

        siblings = self.siblings

        return self.swap_with(siblings[siblings.index(self) - 1])

    def add_sibling(self) -> Self:
        raise NotImplementedError  # pragma: no cover

    def shift_down(self) -> bool:
        """
        Move one place down in the stored order
        """

        if self.is_last_sibling():
            return False

        siblings = self.siblings

        return self.swap_with(siblings[siblings.index(self) + 1])

    def drop(self) -> None:
        manager.delete(self)

    def save(self) -> None:
        manager.save(self)

    # ------------------- Moving between levels --------------------

    def _renumber(self, models: List[Self]) -> None:
        """
        Renumber a whole run in the given order (fixes gaps and duplicate indexes)
        """

        for order, model in enumerate(models):
            model.order_index = order
            self.session.add(model)

    @property
    def previous_sibling(self) -> Optional[Self]:
        if self.is_first_sibling():
            return None

        siblings = self.siblings
        return siblings[siblings.index(self) - 1]

    @property
    def _children_of_kind(self) -> List[Self]:
        """The items of the same kind filed directly under this one"""

        raise NotImplementedError  # pragma: no cover

    @property
    def _parent_of_kind(self) -> Optional[Self]:
        """The item of the same kind this one is filed under; None at the top level"""

        raise NotImplementedError  # pragma: no cover

    def _place(self, parent: "TodooitModel") -> ChangeT:
        """Reparent under `parent`, fitted to it; returns what that meant, for the bar"""

        raise NotImplementedError  # pragma: no cover

    def indent(self, parent: Optional[Self] = None) -> Optional[ChangeT]:
        """
        Make this the last child of `parent` (default: the previous sibling)

        Returns how it was fitted to its new parent, or None if there is
        nothing to indent under.
        """

        parent = parent or self.previous_sibling

        if parent is None:
            return None

        self._renumber(list(parent._children_of_kind) + [self])
        return self._place(parent)

    def unindent(self) -> Optional[ChangeT]:
        """
        Move this out of the item it's nested in, placing it right after that item

        Returns how it was placed, or None if already top level.
        """

        parent = self._parent_of_kind

        if parent is None:
            return None

        grandparent = parent.parent

        # The parent is an orphan: nowhere to move to
        if grandparent is None:  # pragma: no cover
            return None

        run = [model for model in parent.siblings if model.id != self.id]
        after = run.index(parent) + 1
        self._renumber(run[:after] + [self] + run[after:])

        return self._place(grandparent)
