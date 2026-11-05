"""
The engine: takes keys one at a time and acts on a buffer
"""

from dataclasses import dataclass
from typing import Optional, Tuple

from . import motions
from .buffer import Buffer
from .keymap import VimAction, VimCommand, VimKeymap, VimMotion

MODE_NORMAL = "NORMAL"
MODE_INSERT = "INSERT"

# Commands that mean nothing on a host holding a single line of text
LINE_ONLY = frozenset(
    {VimMotion.UP, VimMotion.DOWN, VimMotion.LINE_ABOVE, VimMotion.LINE_BELOW}
)

DIGITS = frozenset("0123456789")

FORWARD_FINDS = frozenset({VimMotion.FIND_FORWARD, VimMotion.TILL_FORWARD})

# Motions that take the character typed after them, and how far from it each lands
FIND_OFFSETS = {
    VimMotion.FIND_FORWARD: 0,
    VimMotion.FIND_BACKWARD: 0,
    VimMotion.TILL_FORWARD: -1,
    VimMotion.TILL_BACKWARD: 1,
}


@dataclass(frozen=True)
class FindView:
    """What a host can show of a character jump, while it's in play."""

    # Where it started
    origin: Tuple[int, int]

    # Which way it looks from there. None once it has gone back past that, when
    # it looks both ways
    forward: Optional[bool]

    # The places it can land on, top to bottom
    targets: Tuple[Tuple[int, int], ...]


@dataclass
class _ShownFind:
    """A character jump in play, from its start until something else happens."""

    forward: bool
    origin: Tuple[int, int]
    targets: Tuple[Tuple[int, int], ...]
    landed: Tuple[int, int]
    both_ways: bool = False


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

        # A partial command: its count, and its keys so far
        self._count = ""
        self._keys = ""

        # The `f F t T` waiting for its character
        self._finding: Optional[VimMotion] = None

        # The last `f F t T` and its character, for repeating
        self._last_find: Optional[Tuple[VimMotion, str]] = None

        self._shown_find: Optional[_ShownFind] = None

    @property
    def pending(self) -> str:
        """The partial command so far, as typed: `2f`."""

        return self._count + self._keys

    @property
    def find_view(self) -> Optional[FindView]:
        """What to show of a character jump, if one is in play."""

        at = self.buffer.cursor

        if self._finding is not None:
            return FindView(at, self._finding in FORWARD_FINDS, ())

        shown = self._shown_find

        if shown is None:
            return None

        # The cursor went elsewhere without a key, as a click does
        if at != shown.landed:
            self._shown_find = None
            return None

        if shown.both_ways:
            return FindView(shown.origin, None, shown.targets)

        return FindView(
            shown.origin,
            shown.forward,
            tuple(
                place
                for place in shown.targets
                if (place > shown.origin) == shown.forward and place != shown.origin
            ),
        )

    def feed(self, key: str) -> bool:
        """Take one key. True if it was used, False to leave it to the host."""

        if key == "escape":
            return self._escape()

        if self.mode != MODE_NORMAL:
            return False

        if self._finding is not None:
            self._finish_find(key)
            return True

        if self._extends_count(key):
            self._count += key
            return True

        was_pending = bool(self.pending)
        self._keys += key if len(key) == 1 else f"<{key}>"

        if self.keys.continues(self._keys):
            return True

        action = self.keys.action_for(self._keys)

        if action is None or (action in LINE_ONLY and not self.multiline):
            # In the middle of a command, a wrong key only cancels it
            self._cancel()
            self._shown_find = None
            return was_pending

        if isinstance(action, VimMotion) and action in FIND_OFFSETS:
            self._finding = action
            self._shown_find = None
            return True

        count = self._take_count()
        self._run(action, count)
        return True

    def set_mode(self, mode: str) -> None:
        """Change mode, for a host whose own commands do."""

        if mode == self.mode:
            return

        self.mode = mode
        self._cancel()
        self._shown_find = None
        self.buffer.mode_changed(mode)

        if mode == MODE_NORMAL:
            self._clamp()

    def _extends_count(self, key: str) -> bool:
        """
        Whether this digit belongs to a count. A digit carries on a count, but
        starts one only if nothing else wants it: `0` never does.
        """

        if key not in DIGITS or self._keys:
            return False

        if self._count:
            return True

        bound = self.keys.action_for(key) or self.keys.continues(key)

        return key != "0" and not bound

    def _take_count(self) -> int:
        """The count of the command just completed, which ends it. 1 if none."""

        count = int(self._count or 1)
        self._cancel()
        return count

    def _cancel(self) -> None:
        self._count = self._keys = ""
        self._finding = None

    def _escape(self) -> bool:
        if self.pending:
            self._cancel()
            return True

        if self.find_view is not None:
            self._shown_find = None
            return True

        if self.mode != MODE_NORMAL:
            self.set_mode(MODE_NORMAL)
            return True

        return False

    def _run(self, action: VimAction, count: int) -> None:
        if action is VimCommand.INSERT:
            self.set_mode(MODE_INSERT)
            return

        assert isinstance(action, VimMotion)

        if action not in (VimMotion.REPEAT_FIND, VimMotion.REVERSE_FIND):
            self._shown_find = None

        self._move(action, count)
        self._clamp()

    def _move(self, motion: VimMotion, count: int) -> None:
        buffer = self.buffer
        row, column = buffer.cursor
        last_row = buffer.line_count - 1

        if motion is VimMotion.LEFT:
            buffer.move_cursor(row, max(0, column - count))
        elif motion is VimMotion.RIGHT:
            buffer.move_cursor(row, min(column + count, self._last_column(row)))
        elif motion is VimMotion.UP:
            buffer.move_rows(-count)
        elif motion is VimMotion.DOWN:
            buffer.move_rows(count)
        elif motion is VimMotion.WORD_FORWARD:
            self._walk(motions.next_word_start, count)
        elif motion is VimMotion.WORD_BACKWARD:
            self._walk(motions.previous_word_start, count)
        elif motion is VimMotion.WORD_END:
            self._walk(motions.next_word_end, count)
        elif motion is VimMotion.FIRST_NON_BLANK:
            self._to_first_non_blank(min(row + count - 1, last_row))
        elif motion is VimMotion.LAST_CHARACTER:
            below = min(row + count - 1, last_row)
            buffer.move_cursor(below, self._last_column(below))
        elif motion is VimMotion.LINE_ABOVE:
            if row > 0:
                self._to_first_non_blank(max(0, row - count))
        elif motion is VimMotion.LINE_BELOW:
            if row < last_row:
                self._to_first_non_blank(min(row + count, last_row))
        elif motion is VimMotion.REPEAT_FIND:
            self._repeat_find(count, reverse=False)
        elif motion is VimMotion.REVERSE_FIND:
            self._repeat_find(count, reverse=True)

    def _walk(self, step: motions.Step, count: int) -> None:
        """Take `step` up to `count` times, stopping once it gets nowhere."""

        place = self.buffer.cursor

        for _ in range(count):
            reached = step(self.buffer, *place)

            if reached == place:
                break

            place = reached

        self.buffer.move_cursor(*place)

    def _to_first_non_blank(self, row: int) -> None:
        self.buffer.move_cursor(row, motions.first_non_blank(self.buffer.line(row)))

    def _finish_find(self, key: str) -> None:
        """The key after `f F t T`. Only a character means anything there."""

        motion = self._finding
        assert motion is not None

        if len(key) != 1:
            self._cancel()
            return

        self._last_find = (motion, key)
        self._find(motion, key, self._take_count())

    def _repeat_find(self, count: int, *, reverse: bool) -> None:
        if self._last_find is None:
            return

        motion, char = self._last_find

        if self._shown_find is None:
            self._show_find(motion, char)

        forward = (motion in FORWARD_FINDS) != reverse
        self._jump(count, forward, may_stay=False)

    def _find(self, motion: VimMotion, char: str, count: int) -> None:
        self._show_find(motion, char)

        # Standing right by the character already: t and T have arrived
        self._jump(count, motion in FORWARD_FINDS, may_stay=FIND_OFFSETS[motion] != 0)

    def _show_find(self, motion: VimMotion, char: str) -> None:
        at = self.buffer.cursor
        rows = self.buffer.visible_rows if self.multiline else range(at[0], at[0] + 1)
        targets = motions.find_targets(self.buffer, rows, char, FIND_OFFSETS[motion])

        self._shown_find = _ShownFind(motion in FORWARD_FINDS, at, targets, at)

    def _jump(self, count: int, forward: bool, *, may_stay: bool) -> None:
        """Go to the `count`th target along, or nowhere if there aren't that many."""

        shown = self._shown_find
        assert shown is not None

        at = self.buffer.cursor
        along = [
            place
            for place in (shown.targets if forward else reversed(shown.targets))
            if (place > at) == forward and place != at or (may_stay and place == at)
        ]

        if len(along) < count:
            return

        shown.landed = along[count - 1]
        shown.both_ways = shown.both_ways or (
            shown.landed != shown.origin
            and (shown.landed > shown.origin) != shown.forward
        )
        self.buffer.move_cursor(*shown.landed)

    def _clamp(self) -> None:
        """In NORMAL the cursor stands on a character, so never past the last one."""

        row, column = self.buffer.cursor
        last = self._last_column(row)

        if column > last:
            self.buffer.move_cursor(row, last)

    def _last_column(self, row: int) -> int:
        return max(0, len(self.buffer.line(row)) - 1)
