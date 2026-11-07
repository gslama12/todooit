"""
The engine: takes keys one at a time and acts on a buffer
"""

from dataclasses import dataclass
from typing import Callable, Dict, Optional, Tuple

from . import motions
from .buffer import Buffer
from .keymap import (
    VimAction,
    VimCommand,
    VimKeymap,
    VimMotion,
    VimOperator,
    VimTextObject,
)
from .register import Register, RegisterMemory
from .search import MatchSpan, Search, SearchMemory

MODE_NORMAL = "NORMAL"
MODE_INSERT = "INSERT"

# Commands that mean nothing on a host holding a single line of text
LINE_ONLY = frozenset(
    {
        VimMotion.UP,
        VimMotion.DOWN,
        VimMotion.LINE_ABOVE,
        VimMotion.LINE_BELOW,
        VimMotion.HALF_PAGE_UP,
        VimMotion.HALF_PAGE_DOWN,
        VimMotion.TOP,
        VimMotion.BOTTOM,
        VimMotion.PARAGRAPH_UP,
        VimMotion.PARAGRAPH_DOWN,
        VimCommand.CENTER_VIEW,
        VimCommand.PICK_FILES,
        VimCommand.DELETE_LINE,
        VimCommand.YANK_LINE,
        VimCommand.OPEN_BELOW,
        VimCommand.OPEN_ABOVE,
        VimCommand.INDENT_LINE,
        VimCommand.UNINDENT_LINE,
        VimOperator.INDENT,
        VimOperator.UNINDENT,
        VimTextObject.INNER_PARAGRAPH,
        VimTextObject.AROUND_PARAGRAPH,
    }
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

# Motions an operator takes whole lines of, and the character motions that take
# the character they land on along. The rest stop short of it.
LINEWISE = frozenset(
    {
        VimMotion.UP,
        VimMotion.DOWN,
        VimMotion.LINE_ABOVE,
        VimMotion.LINE_BELOW,
        VimMotion.HALF_PAGE_UP,
        VimMotion.HALF_PAGE_DOWN,
        VimMotion.TOP,
        VimMotion.BOTTOM,
    }
)
INCLUSIVE = frozenset({VimMotion.WORD_END, VimMotion.LAST_CHARACTER})

# One level of nesting, and which way each key takes a line
NESTING_LEVEL = "  "
NESTING: Dict[VimAction, int] = {
    VimOperator.INDENT: 1,
    VimOperator.UNINDENT: -1,
    VimCommand.INDENT_LINE: 1,
    VimCommand.UNINDENT_LINE: -1,
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


@dataclass
class _SearchPrompt:
    """A search being typed: what to go back to if it's cancelled, and the text."""

    origin: Tuple[int, int]
    lit_before: Optional[Search]
    count: int
    text: str = ""


class VimEngine:
    """
    One editing session on one buffer. Always starts in NORMAL.

    `multiline=False` switches off `LINE_ONLY`, for a host with one line: their
    keys are left to the host, as if unbound.

    `search_memory` holds the last search, for a host that wants it to outlive
    this engine by handing the same one to the next. `register_memory` is the
    same for the register.
    """

    def __init__(
        self,
        buffer: Buffer,
        keys: VimKeymap,
        *,
        multiline: bool = True,
        search_memory: Optional[SearchMemory] = None,
        register_memory: Optional[RegisterMemory] = None,
    ) -> None:
        self.buffer = buffer
        self.keys = keys
        self.multiline = multiline
        self.mode = MODE_NORMAL

        # A partial command: its count, and its keys so far
        self._count = ""
        self._keys = ""

        # The operator waiting for its motion: which, its count, and its keys
        self._operator: Optional[VimOperator] = None
        self._operator_count = ""
        self._operator_keys = ""

        self._register_memory = register_memory or RegisterMemory()

        # What's on the system clipboard by now is older than anything done here
        if self._register_memory.known_clipboard is None:
            self._register_memory.known_clipboard = buffer.clipboard_text()

        # The `f F t T` waiting for its character
        self._finding: Optional[VimMotion] = None

        # The last `f F t T` and its character, for repeating
        self._last_find: Optional[Tuple[VimMotion, str]] = None

        self._shown_find: Optional[_ShownFind] = None

        # Whether `r` is waiting for its character
        self._replacing = False

        # Where INSERT was last left, for `gi`
        self._last_insert: Optional[Tuple[int, int]] = None

        # Whether the buffer is gathering edits into an undo step
        self._step_open = False

        self._search_memory = search_memory or SearchMemory()
        self._search_prompt: Optional[_SearchPrompt] = None

        # The search whose matches are on show
        self.lit_search: Optional[Search] = None

    @property
    def register(self) -> Optional[Register]:
        """What a paste puts in, unless the system clipboard has news."""

        return self._register_memory.register

    @property
    def search_prompt(self) -> Optional[str]:
        """What's typed in the search prompt, or None if it isn't open."""

        return self._search_prompt.text if self._search_prompt else None

    @property
    def search_matches(self) -> Tuple[MatchSpan, ...]:
        """The matches on show, as the text stands now, top to bottom."""

        return tuple(self.lit_search.matches(self.buffer)) if self.lit_search else ()

    @property
    def pending(self) -> str:
        """The partial command so far, as typed: `2d3f`."""

        return self._operator_count + self._operator_keys + self._count + self._keys

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

        # A command is one undo step, unless it ends in INSERT: that step lasts
        # until INSERT does
        if self.mode == MODE_NORMAL:
            self._open_step()

        used = self._take_key(key)

        if self.mode == MODE_NORMAL:
            self._close_step()

        return used

    def _open_step(self) -> None:
        if not self._step_open:
            self._step_open = True
            self.buffer.begin_undo_step()

    def _close_step(self) -> None:
        if self._step_open:
            self._step_open = False
            self.buffer.end_undo_step()

    def _take_key(self, key: str) -> bool:
        if key == "escape":
            return self._escape()

        if self._search_prompt is not None:
            self._feed_search_prompt(self._search_prompt, key)
            return True

        if self.mode != MODE_NORMAL:
            return False

        if self._finding is not None:
            self._finish_find(key)
            return True

        if self._replacing:
            self._finish_replace(key)
            return True

        if self._extends_count(key):
            self._count += key
            return True

        was_pending = bool(self.pending)
        self._keys += key if len(key) == 1 else f"<{key}>"

        if self._operator is None:
            action = self.keys.action_for(self._keys)

            if not isinstance(action, VimOperator) and self.keys.continues(self._keys):
                return True
        else:
            whole = self._operator_keys + self._keys
            action = self.keys.action_for(whole)

            if action is None:
                if self.keys.continues(
                    self._keys, behind_operator=True
                ) or self.keys.continues(whole):
                    return True

                action = self.keys.action_for(self._keys)

                # Only a motion or a text object can follow an operator
                if not isinstance(action, (VimMotion, VimTextObject)):
                    action = None

        if action is None or (action in LINE_ONLY and not self.multiline):
            # In the middle of a command, a wrong key only cancels it
            self._cancel()
            self._shown_find = None
            return was_pending

        if isinstance(action, VimOperator):
            self._operator = action
            self._operator_count, self._operator_keys = self._count, self._keys
            self._count = self._keys = ""
            self._shown_find = None
            return True

        if isinstance(action, VimMotion) and action in FIND_OFFSETS:
            self._finding = action
            self._shown_find = None
            return True

        if action is VimCommand.REPLACE_CHAR:
            self._replacing = True
            self._shown_find = None
            return True

        operator = self._operator
        counted = bool(self._count or self._operator_count)
        count = self._take_count()

        if operator is not None and isinstance(action, VimMotion):
            self._operate(operator, action, count, counted)
        elif operator is not None and isinstance(action, VimTextObject):
            self._operate_on_paragraph(operator, action, count)
        else:
            self._run(action, count, counted)

        return True

    def set_mode(self, mode: str) -> None:
        """Change mode, for a host whose own commands do."""

        if mode == self.mode:
            return

        if self.mode == MODE_INSERT:
            self._last_insert = self.buffer.cursor

        if mode == MODE_INSERT:
            self._open_step()

        self.mode = mode
        self._cancel()
        self._shown_find = None
        self.buffer.mode_changed(mode)

        if mode == MODE_NORMAL:
            self._clamp()
            self._close_step()

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

        count = int(self._count or 1) * int(self._operator_count or 1)
        self._cancel()
        return count

    def _cancel(self) -> None:
        self._count = self._keys = ""
        self._operator = None
        self._operator_count = self._operator_keys = ""
        self._finding = None
        self._replacing = False
        self._search_prompt = None

    def _escape(self) -> bool:
        if self._search_prompt is not None:
            self._cancel_search_prompt(self._search_prompt)
            return True

        if self.pending:
            self._cancel()
            return True

        if self.find_view is not None:
            self._shown_find = None
            return True

        if self.mode != MODE_NORMAL:
            self.set_mode(MODE_NORMAL)
            return True

        # With nothing on show there's nothing to clear, so it's the host's key
        lit = bool(self.search_matches)
        self.lit_search = None

        return lit

    def _run(self, action: VimAction, count: int, counted: bool) -> None:
        if isinstance(action, VimCommand):
            self._shown_find = None
            cursor = row, column = self.buffer.cursor
            line = self.buffer.line(row)

            if action is VimCommand.INSERT:
                self.set_mode(MODE_INSERT)
            elif action is VimCommand.INSERT_AFTER:
                self._insert_at(row, min(column + 1, len(line)))
            elif action is VimCommand.INSERT_FIRST_NON_BLANK:
                self._insert_at(row, motions.indent_width(line))
            elif action is VimCommand.INSERT_LINE_END:
                self._insert_at(row, len(line))
            elif action is VimCommand.INSERT_AT_LAST:
                self._insert_at_last()
            elif action is VimCommand.OPEN_BELOW:
                self._open_below(row)
            elif action is VimCommand.OPEN_ABOVE:
                self._open_above(row)
            elif action is VimCommand.CHANGE_LINE:
                self._change_lines(row, row + count - 1)
            elif action is VimCommand.CHANGE_TO_LINE_END:
                self._operate(
                    VimOperator.CHANGE, VimMotion.LAST_CHARACTER, count, counted
                )
            elif action in NESTING:
                self._nest_lines(row, row + count - 1, NESTING[action])
            elif action is VimCommand.CENTER_VIEW:
                self.buffer.center_view()
            elif action is VimCommand.OPEN_LINK:
                self.buffer.open_link()
            elif action is VimCommand.PICK_FILES:
                self.buffer.pick_files()
            elif action is VimCommand.DELETE_LINE:
                self._delete_lines(row, row + count - 1)
            elif action is VimCommand.DELETE_TO_LINE_END:
                self._operate(
                    VimOperator.DELETE, VimMotion.LAST_CHARACTER, count, counted
                )
            elif action is VimCommand.DELETE_CHAR:
                self._operate(VimOperator.DELETE, VimMotion.RIGHT, count, counted)
            elif action is VimCommand.YANK_LINE:
                self._yank_lines(row, row + count - 1)
            elif action is VimCommand.PASTE_AFTER:
                self._paste(count, before=False)
            elif action is VimCommand.PASTE_BEFORE:
                self._paste(count, before=True)
            elif action is VimCommand.UNDO:
                self._walk_history(self.buffer.undo, count)
            elif action is VimCommand.REDO:
                self._walk_history(self.buffer.redo, count)
            elif action is VimCommand.SEARCH:
                self._search_prompt = _SearchPrompt(cursor, self.lit_search, count)
                self.buffer.prompt_changed()
            elif action is VimCommand.SEARCH_WORD:
                self._search_word(cursor, count)

            return

        assert isinstance(action, VimMotion)

        if action not in (VimMotion.REPEAT_FIND, VimMotion.REVERSE_FIND):
            self._shown_find = None

        self._move(action, count, counted)
        self._clamp()

    def _walk_history(self, step: Callable[[], None], count: int) -> None:
        for _ in range(count):
            step()

        self._clamp()

    def _move(self, motion: VimMotion, count: int, counted: bool) -> None:
        buffer = self.buffer
        row, column = buffer.cursor
        last_row = buffer.line_count - 1

        if motion is VimMotion.LEFT:
            buffer.move_cursor(row, max(0, column - count))
        elif motion is VimMotion.RIGHT:
            buffer.move_cursor(row, min(column + count, self._last_column(row)))
        elif motion is VimMotion.UP:
            (buffer.move_lines if counted else buffer.move_rows)(-count)
        elif motion is VimMotion.DOWN:
            (buffer.move_lines if counted else buffer.move_rows)(count)
        elif motion is VimMotion.HALF_PAGE_UP:
            buffer.scroll_rows(-count * buffer.half_page)
        elif motion is VimMotion.HALF_PAGE_DOWN:
            buffer.scroll_rows(count * buffer.half_page)
        elif motion is VimMotion.TOP:
            buffer.move_lines(min(count - 1 if counted else 0, last_row) - row)
        elif motion is VimMotion.BOTTOM:
            buffer.move_lines(min(count - 1 if counted else last_row, last_row) - row)
        elif motion is VimMotion.PARAGRAPH_UP:
            self._walk(motions.previous_paragraph, count)
        elif motion is VimMotion.PARAGRAPH_DOWN:
            self._walk(motions.next_paragraph, count)
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
        elif motion is VimMotion.SEARCH_NEXT:
            self._repeat_search(count, forward=True)
        elif motion is VimMotion.SEARCH_PREVIOUS:
            self._repeat_search(count, forward=False)

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
        operator = self._operator
        assert motion is not None

        if len(key) != 1:
            self._cancel()
            return

        self._last_find = (motion, key)
        origin = self.buffer.cursor
        found = self._find(motion, key, self._take_count())

        if operator is not None:
            self._operate_on_find(operator, origin, found, motion in FORWARD_FINDS)

    def _repeat_find(self, count: int, *, reverse: bool) -> bool:
        if self._last_find is None:
            return False

        motion, char = self._last_find

        if self._shown_find is None:
            self._show_find(motion, char)

        forward = (motion in FORWARD_FINDS) != reverse

        return self._jump(count, forward, may_stay=False)

    def _find(self, motion: VimMotion, char: str, count: int) -> bool:
        self._show_find(motion, char)

        # Standing right by the character already: t and T have arrived
        return self._jump(
            count, motion in FORWARD_FINDS, may_stay=FIND_OFFSETS[motion] != 0
        )

    def _show_find(self, motion: VimMotion, char: str) -> None:
        at = self.buffer.cursor
        rows = self.buffer.visible_rows if self.multiline else range(at[0], at[0] + 1)
        targets = motions.find_targets(self.buffer, rows, char, FIND_OFFSETS[motion])

        self._shown_find = _ShownFind(motion in FORWARD_FINDS, at, targets, at)

    def _jump(self, count: int, forward: bool, *, may_stay: bool) -> bool:
        """
        Go to the `count`th target along, or nowhere if there aren't that many.
        True if it got one, even one it was already on.
        """

        shown = self._shown_find
        assert shown is not None

        at = self.buffer.cursor
        along = [
            place
            for place in (shown.targets if forward else reversed(shown.targets))
            if (place > at) == forward and place != at or (may_stay and place == at)
        ]

        if len(along) < count:
            return False

        shown.landed = along[count - 1]
        shown.both_ways = shown.both_ways or (
            shown.landed != shown.origin
            and (shown.landed > shown.origin) != shown.forward
        )
        self.buffer.move_cursor(*shown.landed)
        return True

    def _feed_search_prompt(self, prompt: _SearchPrompt, key: str) -> None:
        """A key while typing a search. Only characters mean anything but these."""

        if key == "enter":
            self._confirm_search_prompt(prompt)
            return

        if key == "backspace":
            if not prompt.text:
                self._cancel_search_prompt(prompt)
                return

            prompt.text = prompt.text[:-1]
        elif len(key) == 1:
            prompt.text += key
        else:
            return

        # Always from where it began, so the text alone decides where it stands
        search = Search(prompt.text) if prompt.text else None
        hit = search.next_from(self.buffer, prompt.origin, forward=True) if search else None

        self.lit_search = search or prompt.lit_before
        self.buffer.move_cursor(*(hit.place if hit else prompt.origin))
        self.buffer.prompt_changed()

    def _confirm_search_prompt(self, prompt: _SearchPrompt) -> None:
        self._search_prompt = None
        self.buffer.prompt_changed()

        # Nothing typed means the last search again
        search = Search(prompt.text) if prompt.text else self._search_memory.last

        if search is not None:
            self._search(search, prompt.count, prompt.origin, forward=True)

    def _cancel_search_prompt(self, prompt: _SearchPrompt) -> None:
        self._search_prompt = None
        self.lit_search = prompt.lit_before
        self.buffer.move_cursor(*prompt.origin)
        self.buffer.prompt_changed()

    def _search_word(self, cursor: Tuple[int, int], count: int) -> None:
        row, column = cursor
        line = self.buffer.line(row)
        word = motions.word_at(line, column)

        if word is None:
            self.buffer.report("No word under the cursor")
            return

        start, end = word
        search = Search(line[start:end], whole_word=True)
        self._search(search, count, (row, start), forward=True)

    def _repeat_search(self, count: int, *, forward: bool) -> None:
        last = self._search_memory.last

        if last is None:
            self.buffer.report("No search yet")
            return

        self._search(last, count, self.buffer.cursor, forward=forward)

    def _search(
        self, search: Search, count: int, place: Tuple[int, int], *, forward: bool
    ) -> None:
        """Make `search` the last one and light it up, then go `count` matches along."""

        self._search_memory.last = self.lit_search = search
        wrapped = False

        for _ in range(count):
            hit = search.next_from(self.buffer, place, forward=forward)

            if hit is None:
                self.buffer.report(f"Not found: {search.text}")
                return

            place = hit.place
            wrapped = wrapped or hit.wrapped

        self.buffer.move_cursor(*place)

        if wrapped:
            end = "top" if forward else "bottom"
            self.buffer.report(f"Search wrapped to the {end}")

    def _operate(
        self, operator: VimOperator, motion: VimMotion, count: int, counted: bool
    ) -> None:
        """Carry out `operator` over what `motion` goes across from the cursor."""

        self._shown_find = None

        buffer = self.buffer
        origin = row, column = buffer.cursor

        if motion in LINEWISE:
            self._operate_on_lines(operator, motion, count, counted)
        elif motion in (VimMotion.REPEAT_FIND, VimMotion.REVERSE_FIND):
            reverse = motion is VimMotion.REVERSE_FIND
            found = self._repeat_find(count, reverse=reverse)

            # Takes the character it lands on only going forward
            last = self._last_find
            forward = last is not None and last[0] in FORWARD_FINDS
            self._operate_on_find(operator, origin, found, forward != reverse)
        elif motion is VimMotion.RIGHT:
            # The one place the cursor can't go, so not by moving it there
            self._operate_on_text(
                operator,
                origin,
                (row, min(column + count, len(buffer.line(row)))),
                False,
            )
        elif motion is VimMotion.WORD_FORWARD:
            self._walk(motions.next_word_start, count - 1)
            # `cw` leaves the blanks after a word, unless it started on blanks
            stops_at_word = (
                operator is VimOperator.CHANGE
                and not buffer.line(row)[column : column + 1].isspace()
            )
            last_word_end = (
                motions.word_change_end if stops_at_word else motions.word_operand_end
            )
            end = last_word_end(buffer, *buffer.cursor)
            self._operate_on_text(operator, origin, end, False)
        else:
            self._move(motion, count, counted)
            target = buffer.cursor

            # `}` with no blank line left has the note's last character to take
            inclusive = motion in INCLUSIVE or (
                motion is VimMotion.PARAGRAPH_DOWN and bool(buffer.line(target[0]))
            )

            # Going nowhere is a motion that failed, so nothing to act on. Only
            # `=` can't fail by standing where it goes.
            if (
                target == origin
                and not inclusive
                and motion is not VimMotion.FIRST_NON_BLANK
            ):
                return

            self._operate_on_text(operator, origin, target, inclusive)

    def _operate_on_paragraph(
        self, operator: VimOperator, text_object: VimTextObject, count: int
    ) -> None:
        self._shown_find = None

        row = self.buffer.cursor[0]

        if text_object is VimTextObject.AROUND_PARAGRAPH:
            top, bottom = motions.around_paragraph_lines(self.buffer, row, count)
        else:
            top, bottom = motions.paragraph_lines(self.buffer, row, count)

        self._take_lines(operator, top, bottom)

    def _operate_on_find(
        self,
        operator: VimOperator,
        origin: Tuple[int, int],
        found: bool,
        inclusive: bool,
    ) -> None:
        """The operator's turn after a jump, which took the cursor there already."""

        self._shown_find = None

        if found:
            self._operate_on_text(operator, origin, self.buffer.cursor, inclusive)

    def _operate_on_lines(
        self, operator: VimOperator, motion: VimMotion, count: int, counted: bool
    ) -> None:
        """A motion that takes whole lines, worked out by line, never by screen row."""

        buffer = self.buffer
        row = buffer.cursor[0]
        last = buffer.line_count - 1

        if motion in (VimMotion.TOP, VimMotion.BOTTOM):
            end = last if motion is VimMotion.BOTTOM else 0
            target = min(count - 1, last) if counted else end
        else:
            if motion in (VimMotion.HALF_PAGE_UP, VimMotion.HALF_PAGE_DOWN):
                count *= buffer.half_page

            up = motion in (
                VimMotion.UP,
                VimMotion.LINE_ABOVE,
                VimMotion.HALF_PAGE_UP,
            )
            target = max(0, row - count) if up else min(row + count, last)

            # Nowhere to go is a motion that failed, so nothing to act on
            if target == row:
                return

        self._take_lines(operator, min(row, target), max(row, target))

    def _operate_on_text(
        self,
        operator: VimOperator,
        origin: Tuple[int, int],
        target: Tuple[int, int],
        inclusive: bool,
    ) -> None:
        """
        Take what's between two places in either order, then stand where it was:
        in INSERT, if it's a change, even with nothing there to take. Nesting
        takes no text, only the lines it touches.
        """

        start, end = sorted((origin, target))
        buffer = self.buffer

        if inclusive:
            end = end[0], min(end[1] + 1, len(buffer.line(end[0])))
        elif end[1] == 0 and end[0] > start[0]:
            # Stopping short of a line's start: the line break stays out of it,
            # and from a line's start that makes it whole lines
            if not buffer.line(start[0])[: start[1]].strip():
                self._take_lines(operator, start[0], end[0] - 1, column=origin[1])
                return

            end = end[0] - 1, len(buffer.line(end[0] - 1))

        if operator in NESTING:
            self._nest_lines(start[0], end[0], NESTING[operator])
            return

        if start != end:
            text = self._text_between(start, end)

            if operator is VimOperator.YANK:
                self._yank(text, linewise=False)
            else:
                self._register_memory.register = Register(text, linewise=False)
                buffer.replace(start, end, "")

        if operator is VimOperator.CHANGE:
            self._insert_at(*start)
            return

        buffer.move_cursor(*start)
        self._clamp()

    def _take_lines(
        self,
        operator: VimOperator,
        top: int,
        bottom: int,
        *,
        column: Optional[int] = None,
    ) -> None:
        if operator is VimOperator.YANK:
            self._yank_lines(top, bottom, column=column)
        elif operator is VimOperator.CHANGE:
            self._change_lines(top, bottom)
        elif operator in NESTING:
            self._nest_lines(top, bottom, NESTING[operator])
        else:
            self._delete_lines(top, bottom, column=column)

    def _delete_lines(
        self, top: int, bottom: int, *, column: Optional[int] = None
    ) -> None:
        """Delete these lines, whatever is below or above to close the gap with."""

        buffer = self.buffer
        last = buffer.line_count - 1
        bottom = min(bottom, last)

        if column is None:
            column = buffer.cursor[1]

        self._register_memory.register = Register(
            self._lines_between(top, bottom), linewise=True
        )

        if bottom < last:
            buffer.replace((top, 0), (bottom + 1, 0), "")
        elif top > 0:
            above = top - 1, len(buffer.line(top - 1))
            buffer.replace(above, (bottom, len(buffer.line(bottom))), "")
        else:
            buffer.replace((0, 0), (bottom, len(buffer.line(bottom))), "")

        row = min(top, buffer.line_count - 1)
        buffer.move_cursor(row, min(column, self._last_column(row)))

    def _change_lines(self, top: int, bottom: int) -> None:
        """Empty these lines into one, keeping the first's indent and marker."""

        buffer = self.buffer
        bottom = min(bottom, buffer.line_count - 1)
        end = bottom, len(buffer.line(bottom))
        first = buffer.line(top)
        prefix = len(buffer.list_prefix(top))
        keep = first[: prefix + motions.indent_width(first[prefix:])]

        self._register_memory.register = Register(
            self._lines_between(top, bottom), linewise=True
        )
        buffer.replace((top, 0), end, keep)
        self._insert_at_line_end(top)

    def _yank(self, text: str, *, linewise: bool) -> None:
        memory = self._register_memory
        memory.register = Register(text, linewise)
        memory.known_clipboard = text
        self.buffer.copy_to_clipboard(text)

    def _yank_lines(
        self, top: int, bottom: int, *, column: Optional[int] = None
    ) -> None:
        """Yank these lines, the cursor going no further than the first of them."""

        buffer = self.buffer
        bottom = min(bottom, buffer.line_count - 1)

        if column is None:
            column = buffer.cursor[1]

        self._yank(self._lines_between(top, bottom), linewise=True)
        buffer.move_cursor(top, min(column, self._last_column(top)))

    def _paste(self, count: int, *, before: bool) -> None:
        memory = self._register_memory
        clipboard = self.buffer.clipboard_text()

        if memory.pastes_clipboard(clipboard):
            # Taken up, so it only wins once: a later `ddp` moves its line again
            memory.register = Register(clipboard, False, from_clipboard=True)
            memory.known_clipboard = clipboard

        register = memory.register

        if register is None:
            self.buffer.report("Nothing to paste")
        elif register.from_clipboard:
            self._paste_clipboard_text(register.text, count, before)
        elif register.linewise:
            self._paste_lines(register.text, count, before)
        else:
            self._paste_characters(register.text, count, before)

    def _paste_lines(self, text: str, count: int, before: bool) -> None:
        buffer = self.buffer
        row = buffer.cursor[0]
        pasted = "\n".join([text] * count)

        if before:
            buffer.replace((row, 0), (row, 0), pasted + "\n")
        else:
            end = row, len(buffer.line(row))
            buffer.replace(end, end, "\n" + pasted)
            row += 1

        self._to_first_non_blank(row)

    def _paste_characters(self, text: str, count: int, before: bool) -> None:
        start = self._paste_place(before)
        self.buffer.replace(start, start, text * count)

        if "\n" in text:
            self.buffer.move_cursor(*start)
        else:
            self.buffer.move_cursor(start[0], start[1] + len(text) * count - 1)

        self._clamp()

    def _paste_clipboard_text(self, text: str, count: int, before: bool) -> None:
        """
        The host makes what it likes of this, so only it knows how long it came
        out. Goes by way of INSERT, as only that can stand past a line's last
        character, but it's no insert that `gi` should remember.
        """

        buffer = self.buffer
        last_insert = self._last_insert
        start = self._paste_place(before)

        self._insert_at(*start)

        for _ in range(count):
            buffer.paste_clipboard_text(text)

        row, column = buffer.cursor

        if row == start[0]:
            buffer.move_cursor(row, max(start[1], column - 1))
        else:
            buffer.move_cursor(*start)

        self.set_mode(MODE_NORMAL)
        self._last_insert = last_insert

    def _paste_place(self, before: bool) -> Tuple[int, int]:
        row, column = self.buffer.cursor

        if before:
            return row, column

        return row, min(column + 1, len(self.buffer.line(row)))

    def _nest_lines(self, top: int, bottom: int, levels: int) -> None:
        """Move these lines in or out, and stand on the first one's first non-blank."""

        buffer = self.buffer

        for row in range(top, min(bottom, buffer.line_count - 1) + 1):
            self._nest_line(row, levels)

        self._to_first_non_blank(top)

    def _nest_line(self, row: int, levels: int) -> None:
        """Rewrite the line's indent to a whole level; an empty line has none to move."""

        buffer = self.buffer
        start = buffer.nesting_start(row)
        body = buffer.line(row)[start:]

        if not body:
            return

        width = motions.indent_width(body)
        indent = body[:width]
        size = len(NESTING_LEVEL)
        depth = max(0, len(indent.expandtabs(size)) // size + levels)
        nested = NESTING_LEVEL * depth

        if nested != indent:
            buffer.replace((row, start), (row, start + width), nested)

    def _finish_replace(self, key: str) -> None:
        """The key after `r`. Only a character means anything there."""

        if len(key) != 1:
            self._cancel()
            return

        count = self._take_count()
        buffer = self.buffer
        row, column = buffer.cursor

        # As in vim: it takes all of them or none
        if column + count > len(buffer.line(row)):
            return

        buffer.replace((row, column), (row, column + count), key * count)
        buffer.move_cursor(row, column + count - 1)

    def _open_below(self, row: int) -> None:
        buffer = self.buffer
        end = row, len(buffer.line(row))

        buffer.replace(end, end, "\n" + buffer.list_prefix(row))
        self._insert_at_line_end(row + 1)

    def _open_above(self, row: int) -> None:
        buffer = self.buffer

        buffer.replace((row, 0), (row, 0), buffer.list_prefix(row) + "\n")
        self._insert_at_line_end(row)

    def _insert_at_last(self) -> None:
        """Where INSERT was last left, as near as the text allows now."""

        row, column = self._last_insert or self.buffer.cursor
        row = min(row, self.buffer.line_count - 1)

        self._insert_at(row, min(column, len(self.buffer.line(row))))

    def _insert_at_line_end(self, row: int) -> None:
        # Read only now: the host may have counted a list again, changing its width
        self._insert_at(row, len(self.buffer.line(row)))

    def _insert_at(self, row: int, column: int) -> None:
        """INSERT first, as only INSERT can stand after a line's last character."""

        self.set_mode(MODE_INSERT)
        self.buffer.move_cursor(row, column)

    def _lines_between(self, top: int, bottom: int) -> str:
        return "\n".join(self.buffer.line(row) for row in range(top, bottom + 1))

    def _text_between(self, start: Tuple[int, int], end: Tuple[int, int]) -> str:
        if start[0] == end[0]:
            return self.buffer.line(start[0])[start[1] : end[1]]

        middle = [self.buffer.line(row) for row in range(start[0] + 1, end[0])]

        return "\n".join(
            [
                self.buffer.line(start[0])[start[1] :],
                *middle,
                self.buffer.line(end[0])[: end[1]],
            ]
        )

    def _clamp(self) -> None:
        """In NORMAL the cursor stands on a character, so never past the last one."""

        row, column = self.buffer.cursor
        last = self._last_column(row)

        if column > last:
            self.buffer.move_cursor(row, last)

    def _last_column(self, row: int) -> int:
        return max(0, len(self.buffer.line(row)) - 1)
