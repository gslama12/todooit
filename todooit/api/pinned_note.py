from sqlalchemy.orm import Mapped, mapped_column

from .manager import manager
from .model import BaseModel, BaseModelMixin


# The table holds exactly one row, always with this id
PINNED_NOTE_ID = 1


class PinnedNote(BaseModel, BaseModelMixin):
    """
    The global scratchpad note, stored in the DB so it travels with the todos
    """

    id: Mapped[int] = mapped_column(primary_key=True, default=PINNED_NOTE_ID)
    note: Mapped[str] = mapped_column(default="")

    # File paths, one per line (as on a todo)
    attachments: Mapped[str] = mapped_column(default="")

    @classmethod
    def instance(cls) -> "PinnedNote":
        """
        The single row, created on first access
        """

        row = manager.session.get(cls, PINNED_NOTE_ID)

        if row is None:
            row = cls(id=PINNED_NOTE_ID, note="")
            manager.save(row)

        return row

    @classmethod
    def get_text(cls) -> str:
        return cls.instance().note or ""

    @classmethod
    def get_attachments(cls) -> str:
        return cls.instance().attachments or ""

    @classmethod
    def set_attachments(cls, text: str) -> None:
        """
        Save the attachments, skipping the commit if unchanged
        """

        row = cls.instance()

        if row.attachments == text:
            return

        row.attachments = text
        manager.save(row)

    @classmethod
    def set_text(cls, text: str) -> None:
        """
        Save the note, skipping the commit if unchanged (the editor saves repeatedly)
        """

        row = cls.instance()

        if row.note == text:
            return

        row.note = text
        manager.save(row)
