"""
The two keyboard modes and moving between them
"""

from ..disp.view import NoteView
from .host import EditorHost

# Keyboard mode: NORMAL reads/moves, INSERT types (same names as the status bar).
MODE_NORMAL = "NORMAL"
MODE_INSERT = "INSERT"


class ModalEditor(NoteView):
    """NORMAL reads and moves; INSERT types. `read_only` is what NORMAL *is*."""

    def __init__(self, text: str) -> None:
        # read_only is what NORMAL *is*; starts read_only unless there's
        # non-whitespace to read. tab_behavior stays "focus" so escape bubbles.
        super().__init__(text, read_only=bool(text.strip()))

    @property
    def host(self) -> EditorHost:
        """The window this editor is in."""

        screen = self.screen

        assert isinstance(screen, EditorHost)
        return screen

    @property
    def mode(self) -> str:
        return MODE_NORMAL if self.read_only else MODE_INSERT

    def enter_insert(self) -> None:
        if not self.read_only:
            return

        self.read_only = False
        self.host.mode_changed()

    def enter_normal(self) -> None:
        if self.read_only:
            return

        self.read_only = True
        self.host.mode_changed()
