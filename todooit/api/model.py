from typing import Any, List
from typing_extensions import Self
from sqlalchemy.orm import DeclarativeBase, Mapped, mapped_column
from sqlalchemy.ext.declarative import declared_attr
from .manager import manager


class BaseModel(DeclarativeBase):
    pass


class BaseModelMixin:
    @declared_attr
    def __tablename__(cls):
        return cls.__name__.lower()


class TodooitModel(BaseModel, BaseModelMixin):
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
