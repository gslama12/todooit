from typing import TYPE_CHECKING, Optional, Tuple

from rich.style import Style
from rich.text import Text

from todooit.utils.clipboard import copy_text, paste_text, running_app

if TYPE_CHECKING:  # pragma: no cover
    from todooit.api.lifecycle import Outcome

# Keys that discard the selection instead of editing it (`ctrl+l` excluded: it always clears the whole buffer).
SELECTION_DELETE_KEYS = frozenset(
    {"backspace", "delete", "ctrl+w", "ctrl+delete", "alt+d"}
)

# Keys that grow/shrink a selection: anchor stays put, cursor moves as it would without shift.
SELECTION_EXTEND_KEYS = frozenset(
    {
        "shift+left",
        "shift+right",
        "ctrl+shift+left",
        "ctrl+shift+right",
        "alt+shift+left",
        "alt+shift+right",
        "shift+home",
        "shift+end",
    }
)

# Reserved cell past the last character, so the field doesn't grow/shrink by a column as the cursor arrives/leaves.
CURSOR_REST = " "


class Input:
    """A simple single line Text Input."""

    is_editing = False

    # Selection start; cursor is the other end. None, or anchor==cursor, means no selection.
    _selection_anchor: Optional[int] = None

    # Inputs that only show a derived value refuse to be edited
    editable: bool = True

    def __init__(self, value="") -> None:
        self._value = value
        self._cursor_position = len(self._value)
        self._selection_anchor = None

    @property
    def value(self) -> str:
        return self._value

    @property
    def cursor_position(self) -> int:
        return self._cursor_position

    def move_cursor(self, position: int) -> None:
        """Put the cursor at `position`, which ends any selection."""

        self._cursor_position = max(0, min(position, len(self._value)))
        self._selection_anchor = None

    def replace(self, start: int, end: int, text: str) -> None:
        """Swap a span of the buffer for `text`, cursor left after it (used by completion)."""

        self._value = self._value[:start] + text + self._value[end:]
        self._cursor_position = start + len(text)
        self._selection_anchor = None

    @property
    def selection(self) -> Optional[Tuple[int, int]]:
        """The selected span as (start, end), or None when nothing is selected."""

        if self._selection_anchor is None:
            return None

        start, end = sorted((self._selection_anchor, self._cursor_position))

        if start == end:
            return None

        return start, end

    @property
    def selected_text(self) -> str:
        span = self.selection

        if span is None:
            return ""

        return self._value[span[0] : span[1]]

    def render_editing(self, theme) -> Text:
        """
        What to draw while this field is being edited. Bypasses formatters, so
        subclasses override to show something useful about the half-typed
        buffer (e.g. what a due-date expression resolves to). Selection is
        drawn as a highlighted block with no separate cursor glyph.
        """

        # Buffer, not `value`, and unstripped: leading/trailing spaces are live content while editing.
        text = Text(self._value + CURSOR_REST)
        self.editing_marks(text, theme)

        span = self.selection

        if span is not None:
            # Stylize the span, not the whole Text, so an appended preview (e.g. due-date) stays outside the highlight.
            text.stylize(self.selection_style(theme), *span)
        else:
            # Style the character under the cursor instead of inserting a glyph, so columns don't shift.
            text.stylize(
                self.editing_cursor_style(theme),
                self._cursor_position,
                self._cursor_position + 1,
            )

        return text

    @staticmethod
    def selection_style(theme) -> Style:
        """The inverted pill style the bar wears while a field is being edited."""

        return Style(color=theme.background1, bgcolor=theme.secondary)

    @staticmethod
    def cursor_style(theme) -> Style:
        """A terminal-style block cursor with the character punched back out."""

        return Style(color=theme.background1, bgcolor=theme.primary)

    def editing_marks(self, text: Text, theme) -> None:
        """Anything to show on the buffer beneath the cursor; nothing, for a plain field."""

    def editing_cursor_style(self, theme) -> Style:
        """The cursor as it's drawn right now, which a mode of its own may change."""

        return self.cursor_style(theme)

    def start_edit(self) -> None:
        self.is_editing = True

        # Start with the value fully selected, so typing replaces it directly.
        self._cursor_position = len(self._value)
        self._selection_anchor = 0

    def stop_edit(self, cancel: bool = False) -> Optional["Outcome"]:
        self.is_editing = False
        self._selection_anchor = None
        return None

    def _is_text_key(self, key: str) -> bool:
        """Whether this keypress puts something into the buffer."""

        return (
            key in ("space", "tab", "ctrl+v")
            or key.startswith("events.Paste:")
            or len(key) == 1
        )

    def _settle_selection(self, key: str, span: Tuple[int, int]) -> None:
        """Delete the selection if `key` writes or deletes; otherwise leave the value alone."""

        if key in SELECTION_DELETE_KEYS or self._is_text_key(key):
            start, end = span
            self._value = self._value[:start] + self._value[end:]
            self._cursor_position = start

    def select_all(self) -> None:
        """Select the whole buffer."""

        self._selection_anchor = 0
        self.move_cursor_to_end()

    def _extend_selection(self, key: str) -> None:
        """Move the cursor, leaving the anchor behind to grow the selection."""

        if self._selection_anchor is None:
            self._selection_anchor = self._cursor_position

        if key == "shift+left":
            self._move_cursor_backward()

        elif key == "shift+right":
            self._move_cursor_forward()

        elif key in ("ctrl+shift+left", "alt+shift+left"):
            self._move_cursor_backward(word=True)

        elif key in ("ctrl+shift+right", "alt+shift+right"):
            self._move_cursor_forward(word=True)

        elif key == "shift+home":
            self._cursor_position = 0

        elif key == "shift+end":
            self.move_cursor_to_end()

    def copy_selection(self) -> None:
        """Copy the selection, or the whole field if nothing is selected."""

        text = self.selected_text or self._value

        if not text:
            return

        copy_text(running_app(), text)

    def paste_from_clipboard(self) -> None:
        """Insert clipboard text at the cursor, joining multiple lines into one."""

        text = " ".join(paste_text(running_app()).splitlines())

        if text:
            self._insert_text(text)

    def _insert_text(self, text: str) -> None:
        """Inserts text where the cursor is."""

        self._value = (
            self._value[: self._cursor_position]
            + text
            + self._value[self._cursor_position :]
        )

        self._cursor_position += len(text)

    def _move_cursor_backward(self, word=False, delete=False) -> None:
        """Move the cursor backward; `word` jumps a word, `delete` removes it."""

        prev = self._cursor_position

        if not word:
            self._cursor_position = max(self._cursor_position - 1, 0)
        else:
            while self._cursor_position:
                if self._value[self._cursor_position - 1] != " " and (
                    self._cursor_position == 1
                    or self._value[self._cursor_position - 2] == " "
                ):
                    self._cursor_position -= 1
                    break

                self._cursor_position -= 1

        if delete:
            self._value = self._value[: self._cursor_position] + self._value[prev:]

    def _move_cursor_forward(self, word=False, delete=False) -> None:
        """Move the cursor forward; `word` jumps a word, `delete` removes it."""

        prev = self._cursor_position

        if not word:
            self._cursor_position = min(self._cursor_position + 1, len(self._value))
        else:
            while self._cursor_position < len(self._value):
                if (
                    self._cursor_position != prev
                    and self._value[self._cursor_position - 1] == " "
                    and (
                        self._cursor_position == len(self._value) - 1
                        or self._value[self._cursor_position] != " "
                    )
                ):
                    break

                self._cursor_position += 1

        if delete:
            self._value = self._value[:prev] + self._value[self._cursor_position :]
            self._cursor_position = prev  # Because the cursor never actually moved :)

    def clear_input(self) -> None:
        self.move_cursor_to_end()
        while self._value:
            self.keypress("backspace")

    def move_cursor_to_end(self) -> None:
        self._cursor_position = len(self._value)

    def keypress(self, key: str) -> None:
        # These keys extend a selection rather than settling it.
        if key in SELECTION_EXTEND_KEYS:
            self._extend_selection(key)
            return

        if key == "ctrl+a":
            self.select_all()
            return

        # Copy leaves the selection standing, since it's usually about to be replaced.
        if key == "ctrl+c":
            self.copy_selection()
            return

        span = self.selection
        self._selection_anchor = None

        if span is not None:
            self._settle_selection(key, span)

            # Selected text is already gone; don't delete further into what's left.
            if key in SELECTION_DELETE_KEYS:
                return

        # Moving backward
        if key == "left":
            self._move_cursor_backward()

        elif key == "ctrl+left":
            self._move_cursor_backward(word=True)

        elif key == "backspace":
            self._move_cursor_backward(delete=True)

        elif key == "ctrl+w":
            self._move_cursor_backward(word=True, delete=True)

        # Moving forward
        elif key == "right":
            self._move_cursor_forward()

        elif key == "ctrl+right":
            self._move_cursor_forward(word=True)

        elif key == "delete":
            self._move_cursor_forward(delete=True)

        # alt+d: readline's (and a Mac's opt+delete through the terminal)
        elif key in ("ctrl+delete", "alt+d"):
            self._move_cursor_forward(word=True, delete=True)

        # clear all input; ctrl+u is what the terminal sends for cmd+backspace
        elif key in ("ctrl+l", "ctrl+u"):
            self.clear_input()

        # EXTRAS
        # A single line's top/bottom are its start/end
        elif key in ("home", "ctrl+home"):
            self._cursor_position = 0

        elif key in ("end", "ctrl+end"):
            self.move_cursor_to_end()

        elif key == "tab":
            self._insert_text("\t")

        elif key == "space":
            self._insert_text(" ")

        elif key == "ctrl+v":
            self.paste_from_clipboard()

        elif key.startswith("events.Paste:"):
            self._insert_text(key[13:])

        elif len(key) == 1:
            self._insert_text(key)
