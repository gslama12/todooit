"""
The note window, split by concern:

- `disp`    the markup and how it's drawn, including as it's typed
- `vim`     changing the text from the keyboard: modes, keys, clipboard
- `screens` what the user sees: the window, the pinned note, the attachments

Dependencies run one way: `screens` -> `vim` -> `disp`.
"""

from .screens import NoteScreen, NoteScreenBase, PinnedNoteScreen

__all__ = ["NoteScreen", "NoteScreenBase", "PinnedNoteScreen"]
