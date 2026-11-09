"""
INSERT's cursor: the terminal's own, drawn as a slim bar between characters

Textual hides the terminal's cursor and draws its own as a block on a
character, which is NORMAL's cursor. A cell can't hold anything slimmer, so
INSERT, whose cursor goes between characters, has the terminal draw its own.
Textual already takes it to `app.cursor_position` after every frame, for an
IME, so all that's left is to show it as a bar, in the block's color.
"""

from typing import TYPE_CHECKING, Optional
from weakref import WeakKeyDictionary

if TYPE_CHECKING:  # pragma: no cover
    from textual.app import App

# A steady bar, then shown
SHOW = "\x1b[6 q\x1b[?25h"

# Hidden again, in whatever shape the terminal had before
HIDE = "\x1b[?25l\x1b[0 q"

# Its color, and the terminal's own back
COLOR = "\x1b]12;{}\x1b\\"
RESET_COLOR = "\x1b]112\x1b\\"


class SlimCursor:
    """The terminal's cursor, as a bar where the app puts its cursor, or hidden."""

    def __init__(self, app: "App") -> None:
        self._app = app
        self.shown = False

        # The color last asked for, so it's only sent when it changes
        self._color: Optional[str] = None

    def show(self, color: str) -> None:
        if color != self._color:
            self._color = color
            self._write(COLOR.format(color))

        if not self.shown:
            self.shown = True
            self._write(SHOW)

    def hide(self) -> None:
        if self.shown:
            self.shown = False
            self._write(HIDE)

    def restore(self) -> None:
        """Hand the terminal its cursor back as it was, before the app lets go of it."""

        self.hide()

        if self._color is not None:
            self._color = None
            self._write(RESET_COLOR)

    def _write(self, text: str) -> None:
        app = self._app
        driver = app._driver

        # A test has no terminal to tell
        if driver is not None and not app.is_headless:
            driver.write(text)
            driver.flush()


# One per app, kept off it: the app is a plain textual one to whoever asks
_CURSORS: "WeakKeyDictionary[App, SlimCursor]" = WeakKeyDictionary()


def slim_cursor(app: "App") -> SlimCursor:
    """The app's one slim cursor, made the first time it's asked for."""

    cursor = _CURSORS.get(app)

    if cursor is None:
        cursor = _CURSORS[app] = SlimCursor(app)

    return cursor
