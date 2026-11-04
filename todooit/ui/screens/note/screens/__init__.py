"""
What the user sees of a note:

- `screen`      `NoteScreenBase` and the per-todo `NoteScreen`
- `pinned`      `PinnedNoteScreen`, the app-wide scratchpad note
- `attachments` the strip of attached files at the foot of the window
"""

from .pinned import PinnedNoteScreen
from .screen import NoteScreen, NoteScreenBase

__all__ = ["NoteScreen", "NoteScreenBase", "PinnedNoteScreen"]
