"""
The pinned note: one scratchpad note for the whole app, not tied to a todo
"""

from todooit.api import PinnedNote

from .screen import NoteScreenBase

PINNED_TITLE = "Pinned Note"


class PinnedNoteScreen(NoteScreenBase):
    @property
    def title_text(self) -> str:
        return PINNED_TITLE

    def load_note(self) -> str:
        return PinnedNote.get_text()

    def store_note(self, text: str) -> None:
        PinnedNote.set_text(text)

    def load_attachments(self) -> str:
        return PinnedNote.get_attachments()

    def store_attachments(self, text: str) -> None:
        PinnedNote.set_attachments(text)
