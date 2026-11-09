"""
The strip of attached files along the foot of the note window
"""

from pathlib import Path
from typing import TYPE_CHECKING, List, Optional

from rich.cells import cell_len
from rich.style import Style
from rich.text import Text
from textual import events
from textual.widgets import Static

from todooit.api.theme import TodooitThemeBase
from todooit.utils import (
    blend,
    file_icon,
)

if TYPE_CHECKING:  # pragma: no cover
    from .screen import NoteScreenBase


# Gap between files; each file already has a space either side of its own
FILE_GAP = " "

# Every attached file is drawn; the strip grows more rows rather than hiding any


class AttachmentStrip(Static):
    """
    The files a note carries, along the foot of the window inside its frame -
    kept visually and in the database separate from the note text. Takes the
    keyboard while a file is being picked, and hands it back on `escape`.
    """

    DEFAULT_CSS = """
    AttachmentStrip {
        height: auto;
        display: none;
    }
    """

    can_focus = True

    def __init__(self) -> None:
        super().__init__(id="note-files")

        self.paths: List[Path] = []
        self.picked = 0

        # Which files are drawn on which row, computed from window width
        self.rows: List[List[int]] = [[]]

    @property
    def has_the_keyboard(self) -> bool:
        """
        Whether keys land here rather than in the text. Reads `self.screen`
        directly, since `has_focus` is a reactive still catching up mid-`Focus`.
        """

        screen = self.note_screen

        return screen is not None and screen.focused is self

    @property
    def current(self) -> Optional[Path]:
        """The file the strip is standing on, if any."""

        if not self.paths or not 0 <= self.picked < len(self.paths):
            return None

        return self.paths[self.picked]

    def show(self, paths, theme: TodooitThemeBase) -> None:
        """Draw the strip, hiding it when there's nothing to show."""

        self.paths = list(paths)
        self.picked = max(0, min(self.picked, len(self.paths) - 1))
        self.display = bool(self.paths)

        if self.paths:
            self.rows = self._rows()
            self.update(self._drawn(theme))

    def _label(self, path: Path) -> str:
        """One file's label: icon + name, padded with a space either side."""

        return f" {file_icon(path.name)} {path.name} "

    def _rows(self) -> List[List[int]]:
        """Deal files into rows, as many per row as fit; never drops a file."""

        room = self.size.width or 0
        rows: List[List[int]] = [[]]
        used = 0

        for index, path in enumerate(self.paths):
            width = cell_len(self._label(path))
            gap = cell_len(FILE_GAP) if rows[-1] else 0

            if room and rows[-1] and used + gap + width > room:
                rows.append([])
                used = 0
                gap = 0

            rows[-1].append(index)
            used += gap + width

        return rows

    def _drawn(self, theme: TodooitThemeBase) -> Text:
        """The strip painted row by row, picked file lit; muted when not focused."""

        quiet = Style(color=blend(theme.foreground3, theme.background1, 0.25))
        icon = Style(color=blend(theme.secondary, theme.background1, 0.35))
        lit = Style(color=theme.primary, bgcolor=theme.background3, bold=True)

        drawn = Text(no_wrap=True, overflow="ellipsis")

        for row, indexes in enumerate(self.rows):
            if row:
                drawn.append("\n")

            for place, index in enumerate(indexes):
                chip = Text(self._label(self.paths[index]))

                if self.has_the_keyboard and index == self.picked:
                    chip.stylize(lit)
                else:
                    chip.stylize(quiet)
                    chip.stylize(icon, 0, 3)

                if place:
                    drawn.append(FILE_GAP)

                drawn.append_text(chip)

        return drawn

    def row_of(self, index: int) -> int:
        """Which row a file is drawn on."""

        for row, indexes in enumerate(self.rows):
            if index in indexes:
                return row

        return 0

    def step_row(self, step: int) -> bool:
        """Move to the file above/below, same place along the row; False if none."""

        row = self.row_of(self.picked)
        place = self.rows[row].index(self.picked)
        target = row + step

        if not 0 <= target < len(self.rows):
            return False

        indexes = self.rows[target]
        self.picked = indexes[min(place, len(indexes) - 1)]

        return True

    def on_resize(self) -> None:
        """Recompute rows for the new width."""

        self.refresh_strip()

    def on_focus(self) -> None:
        self.keyboard_moved()

    def on_blur(self) -> None:
        self.keyboard_moved()

    def keyboard_moved(self) -> None:
        """Redraw and update the hint line for whoever has focus now."""

        screen = self.note_screen

        if screen is None:
            return

        self.refresh_strip()
        screen.mode_changed()

    @property
    def note_screen(self) -> Optional["NoteScreenBase"]:
        """The window this is in, or None once it's been removed."""

        try:
            screen = self.screen
        except Exception:
            return None

        from .screen import NoteScreenBase

        return screen if isinstance(screen, NoteScreenBase) else None

    def refresh_strip(self) -> None:
        screen = self.note_screen

        if screen is not None:
            self.show(self.paths, screen.api.vars.theme)

    async def _on_key(self, event: events.Key) -> None:
        """Handle a key while the strip has the keyboard; never passed through."""

        event.stop()
        event.prevent_default()

        screen = self.screen
        from .screen import NoteScreenBase

        assert isinstance(screen, NoteScreenBase)

        if screen.awaiting_answer:
            screen.answer(event.key)
            return

        screen.file_key(screen.resolve_key(event))
