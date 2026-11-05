"""
The engine: takes keys one at a time and acts on a buffer
"""

from .buffer import Buffer
from .keymap import VimAction, VimCommand, VimKeymap, VimMotion

MODE_NORMAL = "NORMAL"
MODE_INSERT = "INSERT"

# Commands that mean nothing on a host holding a single line of text
LINE_ONLY = frozenset({VimMotion.UP, VimMotion.DOWN})


class VimEngine:
    """
    One editing session on one buffer. Always starts in NORMAL.

    `multiline=False` switches off `LINE_ONLY`, for a host with one line: their
    keys are left to the host, as if unbound.
    """

    def __init__(
        self, buffer: Buffer, keys: VimKeymap, *, multiline: bool = True
    ) -> None:
        self.buffer = buffer
        self.keys = keys
        self.multiline = multiline
        self.mode = MODE_NORMAL

        # Keys typed so far of a binding that takes several
        self.pending = ""

    def feed(self, key: str) -> bool:
        """Take one key. True if it was used, False to leave it to the host."""

        if key == "escape":
            return self._escape()

        if self.mode != MODE_NORMAL:
            return False

        was_pending = bool(self.pending)
        self.pending += key if len(key) == 1 else f"<{key}>"

        if self.keys.continues(self.pending):
            return True

        action = self.keys.action_for(self.pending)
        self.pending = ""

        if action is None or (action in LINE_ONLY and not self.multiline):
            # In the middle of a binding, a wrong key only cancels it
            return was_pending

        self._run(action)
        return True

    def set_mode(self, mode: str) -> None:
        """Change mode, for a host whose own commands do."""

        if mode == self.mode:
            return

        self.mode = mode
        self.pending = ""
        self.buffer.mode_changed(mode)

        if mode == MODE_NORMAL:
            self._clamp()

    def _escape(self) -> bool:
        if self.pending:
            self.pending = ""
            return True

        if self.mode != MODE_NORMAL:
            self.set_mode(MODE_NORMAL)
            return True

        return False

    def _run(self, action: VimAction) -> None:
        row, column = self.buffer.cursor

        if action is VimMotion.LEFT:
            self.buffer.move_cursor(row, max(0, column - 1))
        elif action is VimMotion.RIGHT:
            self.buffer.move_cursor(row, min(column + 1, self._last_column(row)))
        elif action is VimMotion.UP:
            self.buffer.move_rows(-1)
        elif action is VimMotion.DOWN:
            self.buffer.move_rows(1)
        elif action is VimCommand.INSERT:
            self.set_mode(MODE_INSERT)
            return

        self._clamp()

    def _clamp(self) -> None:
        """In NORMAL the cursor stands on a character, so never past the last one."""

        row, column = self.buffer.cursor
        last = self._last_column(row)

        if column > last:
            self.buffer.move_cursor(row, last)

    def _last_column(self, row: int) -> int:
        return max(0, len(self.buffer.line(row)) - 1)
