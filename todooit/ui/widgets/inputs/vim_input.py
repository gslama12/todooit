"""
A description edited with the note's vim keys, on the single line `Input` holds
"""

from typing import TYPE_CHECKING, Callable, Optional, Tuple

from rich.style import Style
from rich.text import Text

from todooit.utils.clipboard import copy_text, paste_text, running_app
from todooit.vim_engine import DESCRIPTION_ACTIONS, MODE_INSERT, MODE_NORMAL, VimEngine

from ._input import Input
from .simple_input import ModelType, SimpleInput

if TYPE_CHECKING:  # pragma: no cover
    from todooit.ui.api.api_components import VimManager

# Keys that would type in INSERT, which NORMAL never lets through to the field
TYPING_KEYS = frozenset({"space", "tab"})

# Marks the cell INSERT's cursor stands before, drawn as nothing: the pane
# finds it there and has the terminal put its slim cursor on it
SLIM_CURSOR = "slim_cursor"


class DescriptionBuffer:
    """
    Implements the engine's `Buffer` on a one-line field. What only a note has,
    a view, undo of its own, links and files, is left to do nothing.
    """

    def __init__(
        self,
        field: Input,
        *,
        on_mode: Callable[[str], None],
        on_report: Callable[[str], None],
    ) -> None:
        self._field = field
        self._on_mode = on_mode
        self._on_report = on_report

    @property
    def line_count(self) -> int:
        return 1

    @property
    def visible_rows(self) -> range:
        return range(1)

    def line(self, row: int) -> str:
        return self._field.value

    def drawn_line(self, row: int) -> str:
        return self._field.value

    def stored_column(self, row: int, column: int) -> int:
        return column

    @property
    def cursor(self) -> Tuple[int, int]:
        return 0, self._field.cursor_position

    def move_cursor(self, row: int, column: int) -> None:
        self._field.move_cursor(column)

    def select(self, anchor: Tuple[int, int], linewise: bool) -> None:
        pass

    def replace(self, start: Tuple[int, int], end: Tuple[int, int], text: str) -> None:
        self._field.replace(start[1], end[1], text)

    def move_rows(self, delta: int) -> None:
        pass

    def move_lines(self, delta: int) -> None:
        pass

    @property
    def half_page(self) -> int:
        return 1

    def scroll_rows(self, delta: int) -> None:
        pass

    def center_view(self) -> None:
        pass

    def open_link(self) -> None:
        pass

    def pick_files(self) -> None:
        pass

    def show_help(self) -> None:
        pass

    def list_prefix(self, row: int) -> str:
        return ""

    def nesting_start(self, row: int) -> int:
        return 0

    def mode_changed(self, mode: str) -> None:
        self._on_mode(mode)

    def begin_undo_step(self) -> None:
        pass

    def end_undo_step(self) -> None:
        pass

    def undo(self) -> None:
        pass

    def redo(self) -> None:
        pass

    def report(self, message: str) -> None:
        self._on_report(message)

    def prompt_changed(self) -> None:
        pass

    def copy_to_clipboard(self, text: str) -> None:
        copy_text(running_app(), text)

    def clipboard_text(self) -> str:
        return paste_text(running_app())

    def paste_clipboard_text(self, text: str) -> None:
        # One line, as a plain paste into the field makes it
        flat = " ".join(text.splitlines())
        at = self._field.cursor_position
        self._field.replace(at, at, flat)


class VimDescription(SimpleInput[ModelType, str]):
    """
    A description that takes the note's vim keys once `start_vim` is called on
    an edit already started. Until then, and for an edit started without it,
    it's a plain field.
    """

    # One per edit, gone when the edit is
    engine: Optional[VimEngine] = None

    def start_vim(
        self,
        vim: "VimManager",
        *,
        announce: Callable[[str, str], None],
        report: Callable[[str], None],
    ) -> None:
        """
        Hand this edit's keys to a vim engine: INSERT for nothing to work on,
        else NORMAL on the last character. `announce` is told the mode and the
        keys pending whenever either changes.
        """

        self._announce = announce
        self._announced: Optional[Tuple[str, str]] = None

        # Not selected, as `i` has it: in NORMAL a key is a command, not a
        # replacement, and INSERT goes on from what's there
        self._selection_anchor = None

        buffer = DescriptionBuffer(self, on_mode=self._show_mode, on_report=report)
        self.engine = VimEngine(
            buffer,
            vim.keys,
            multiline=False,
            actions=DESCRIPTION_ACTIONS,
            search_memory=vim.search,
            register_memory=vim.register,
        )

        if self.value:
            self.move_cursor(len(self.value) - 1)
            self._show_mode(MODE_NORMAL)
        else:
            self.engine.set_mode(MODE_INSERT)

    def stop_edit(self, cancel: bool = False):
        self.engine = None
        return super().stop_edit(cancel)

    def vim_keypress(self, key: str) -> bool:
        """Take a key of a vim edit. True once it ends the edit, keeping the text."""

        engine = self.engine
        assert engine is not None

        if key == "enter":
            return True

        if engine.mode == MODE_INSERT:
            # Typing is the field's own, with every key it already knows
            if key == "escape":
                engine.feed(key)
            else:
                self.keypress(key)

        # Escape cancels a command half typed, or puts out a jump's targets;
        # with neither, it's done
        elif key == "escape" and not engine.pending and engine.find_view is None:
            return True

        elif not engine.feed(key) and not self._types(key):
            # Keys vim leaves alone still move and edit as they do anywhere
            self.keypress(key)
            self._stand_on_character()

        self._show_mode(engine.mode)
        return False

    @staticmethod
    def _types(key: str) -> bool:
        return len(key) == 1 or key in TYPING_KEYS

    def _stand_on_character(self) -> None:
        """NORMAL stands on a character, never past the last one, as the engine has it."""

        last = max(0, len(self.value) - 1)

        if self.selection is None and self.cursor_position > last:
            self.move_cursor(last)

    def _show_mode(self, mode: str) -> None:
        pending = self.engine.pending if self.engine else ""

        if (mode, pending) != self._announced:
            self._announced = mode, pending
            self._announce(mode, pending)

    @property
    def in_insert(self) -> bool:
        """Whether this is a vim edit in INSERT, whose cursor is the slim one."""

        return self.engine is not None and self.engine.mode == MODE_INSERT

    def editing_cursor_style(self, theme) -> Style:
        if not self.in_insert:
            return super().editing_cursor_style(theme)

        return Style(meta={SLIM_CURSOR: True})

    def editing_marks(self, text: Text, theme) -> None:
        """As in a note: dim what `f F t T` looks across, and light up where it can land."""

        view = self.engine.find_view if self.engine else None

        if view is None:
            return

        # Imported here: the note's screens import the widgets this lives among
        from todooit.ui.screens.note.disp.theme import backdrop_style, target_style

        column = view.origin[1]
        end = len(self.value)

        if view.forward is None:
            text.stylize(backdrop_style(theme), 0, end)
        elif view.forward:
            text.stylize(backdrop_style(theme), column + 1, end)
        else:
            text.stylize(backdrop_style(theme), 0, column)

        for _, target in view.targets:
            text.stylize(target_style(theme), target, target + 1)
