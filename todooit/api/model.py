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


class DooitModel(BaseModel, BaseModelMixin):
    """
    Model class to for the base tree structure
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

    # An item with nobody beside it is at both ends of the run it is the whole
    # of. A todo that outlived its project has no siblings at all, and asking
    # where it sits among them has to answer rather than fall over.
    def is_last_sibling(self) -> bool:
        siblings = self.siblings
        return not siblings or siblings[-1].id == self.id

    def is_first_sibling(self) -> bool:
        siblings = self.siblings
        return not siblings or siblings[0].id == self.id

    @property
    def has_same_parent_kind(self) -> bool:
        raise NotImplementedError  # pragma: no cover

    def swap_with(self, other: Self) -> bool:
        """
        Exchange filed places with another item beside it

        What a move by hand is made of, so that one can be asked for in terms
        of the item to end up beside rather than in terms of a step through
        the filing. A pane draws its rows in an order of its own and leaves
        part of the run out of it altogether, so the item next to the cursor
        and the item next in the filing are often not the same one.

        The two indexes are exchanged rather than nudged past each other by
        one, and the run is numbered straight through first: a run built up by
        hand can have holes in it, or two items filed at the same index, and a
        nudge across either of those moves nothing at all.
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
        Shift the item one place up among its siblings

        One place up the filing, which is not one row up a pane that leaves
        part of the run out of what it draws. That move belongs to the pane,
        and is made with `swap_with`.
        """

        if self.is_first_sibling():
            return False

        siblings = self.siblings

        return self.swap_with(siblings[siblings.index(self) - 1])

    def _add_sibling(self) -> Self:
        raise NotImplementedError  # pragma: no cover

    def add_sibling(self):
        return self._add_sibling()

    def shift_down(self) -> bool:
        """
        Shift the item one place down among its siblings

        One place down the filing; see `shift_up` on what that is not.
        """

        if self.is_last_sibling():
            return False

        siblings = self.siblings

        return self.swap_with(siblings[siblings.index(self) + 1])

    def drop(self) -> None:
        manager.delete(self)

    def save(self) -> None:
        manager.save(self)
