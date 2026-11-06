"""
The note's undo history, in the steps the vim engine marks out
"""

from math import inf
from sys import maxsize
from typing import List, Optional, Tuple

from textual.document._edit import Edit
from textual.document._history import EditHistory

MAX_STEPS = 1000


class UndoStep(List[Edit]):
    """The edits of one step, and where the cursor was before them."""

    cursor: Optional[Tuple[int, int]] = None


class NoteHistory(EditHistory):
    """
    A step is what lies between `begin_step` and `end_step`. Everything upstream
    would split one on, like time, size, a line break or a cursor move, is ignored.
    """

    def __init__(self) -> None:
        super().__init__(MAX_STEPS, inf, maxsize)

        # Where the cursor was when the step under way began; None between steps
        self._start_cursor: Optional[Tuple[int, int]] = None

        # Whether that step has an edit in it, so it's on the stack already
        self._step_on_stack = False

    def begin_step(self, cursor: Tuple[int, int]) -> None:
        self._start_cursor = cursor
        self._step_on_stack = False

    def end_step(self) -> None:
        self._start_cursor = None
        self._step_on_stack = False

    def checkpoint(self) -> None:
        """Upstream's way to end a batch, on a blur or a move. Only `end_step` does."""

    def record(self, edit: Edit) -> None:
        result = edit._edit_result
        assert result is not None

        if not edit.text and not result.replaced_text:
            return

        if not self._step_on_stack or not self._undo_stack:
            step = UndoStep()
            step.cursor = self._start_cursor
            self._undo_stack.append(step)
            self._step_on_stack = self._start_cursor is not None

        self._undo_stack[-1].append(edit)
        self._redo_stack.clear()
