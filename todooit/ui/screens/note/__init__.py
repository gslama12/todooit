"""
The note window, split by concern:

- `markup`      the markdown-ish syntax: constants, regexes, pure line parsing
- `markdown`    the note's markup to and from markdown, for the clipboard
- `document`    TextArea documents that fold markup out of view and hang
                wrapped list items under their first word
- `editor`      the `NoteEditor` widget: modes, keys, clipboard, theme
- `attachments` the strip of attached files at the foot of the window
- `screen`      `NoteScreenBase` and the per-todo `NoteScreen`
- `pinned`      `PinnedNoteScreen`, the app-wide scratchpad note
"""

from .screen import NoteScreen, NoteScreenBase
from .pinned import PinnedNoteScreen

__all__ = ["NoteScreen", "NoteScreenBase", "PinnedNoteScreen"]
