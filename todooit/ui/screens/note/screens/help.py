"""
The note's help pane (space ?): every key the note knows, by mode, as the keymap
has them now
"""

from typing import TYPE_CHECKING, Callable, Dict, List, Optional, Sequence, Tuple, Union

from rich.style import Style
from textual import events
from textual.app import ComposeResult
from textual.containers import VerticalScroll
from textual.widgets import Static

from todooit.vim_engine import (
    MODE_FLASH,
    MODE_INSERT,
    MODE_NORMAL,
    MODE_VISUAL,
    VimAction,
    VimCommand,
    VimMotion,
    VimOperator,
    VimTextObject,
)

from ...help import HelpScreen, TodooitKeyTable, hint
from ..disp.theme import MODE_COLORS
from ..vim.editor import NoteEditor

if TYPE_CHECKING:  # pragma: no cover
    from todooit.ui.api import TodooitAPI

# A key the keymap doesn't hold, worked out from the api: the strip's motions
KeysFrom = Callable[["TodooitAPI"], str]

# What a row's key column is made of, joined by slashes: keymap actions (the row
# is left out if any has no key), keys written as they are, or keys worked out
Part = Union[VimAction, str, KeysFrom]

Row = Tuple[Sequence[Part], str]

M, C, Op, T = VimMotion, VimCommand, VimOperator, VimTextObject

PANEL_TITLE = "Note Keys"

NOTE_WINDOW = "Note window"


def editor_keys(action: str) -> str:
    """The keys the editor binds `action` to itself, outside the keymap."""

    for binding in NoteEditor.BINDINGS:
        if not isinstance(binding, tuple) and binding.action == action:
            return binding.key.split(",")[-1]

    raise KeyError(action)  # pragma: no cover


def strip_moves(api: "TodooitAPI") -> str:
    motions = api.motion_keys()
    return f"{motions.left}{motions.right}"


def flash_labels(api: "TodooitAPI") -> str:
    return api.vars.vim_flash_alphabet[:3] + "…"


VISUAL_SECTION = "VISUAL / V-LINE"

SECTIONS: Dict[str, Sequence[Row]] = {
    MODE_NORMAL: (
        # Motions
        ((M.LEFT, M.RIGHT, M.UP, M.DOWN), "left, right, up, down"),
        (
            (M.WORD_FORWARD, M.WORD_BACKWARD, M.WORD_END),
            "next word, back a word, word end",
        ),
        (
            (M.LINE_START, M.FIRST_NON_BLANK, M.LAST_CHARACTER),
            "line start, first non-blank, line end",
        ),
        ((M.LINE_ABOVE, M.LINE_BELOW), "first non-blank of the line above / below"),
        ((M.FIND_FORWARD, M.FIND_BACKWARD), "find a character forward / back"),
        ((M.TILL_FORWARD, M.TILL_BACKWARD), "up to a character forward / back"),
        ((M.REPEAT_FIND, M.REVERSE_FIND), "repeat the find / the other way"),
        ((M.HALF_PAGE_UP, M.HALF_PAGE_DOWN), "half a page up / down"),
        ((M.TOP, M.BOTTOM), "top / bottom of the note"),
        ((M.PARAGRAPH_UP, M.PARAGRAPH_DOWN), "paragraph up / down"),
        ((C.CENTER_VIEW,), "centre the cursor line"),
        # Operators, then what they take
        (
            (Op.DELETE, Op.CHANGE, Op.YANK),
            "delete, change, yank + motion or text object",
        ),
        ((Op.INDENT, Op.UNINDENT), "nest / unnest + motion"),
        ((T.INNER_WORD, T.AROUND_WORD), "a word, inside / around"),
        ((T.INNER_BIG_WORD, T.AROUND_BIG_WORD), "a WORD, inside / around"),
        ((T.INNER_PARAGRAPH, T.AROUND_PARAGRAPH), "a paragraph, inside / around"),
        ((T.INNER_PARENS, T.AROUND_PARENS), "( ), inside / around; [ ] { } < > too"),
        (
            (T.INNER_DOUBLE_QUOTES, T.AROUND_DOUBLE_QUOTES),
            "quotes, inside / around; ' ` too",
        ),
        # Edits
        ((C.INSERT, C.INSERT_AFTER), "insert before / after the cursor"),
        ((C.INSERT_FIRST_NON_BLANK, C.INSERT_LINE_END), "insert at line start / end"),
        ((C.INSERT_AT_LAST,), "insert where INSERT was left"),
        ((C.OPEN_BELOW, C.OPEN_ABOVE), "open a line below / above"),
        (
            (C.DELETE_LINE, C.DELETE_TO_LINE_END, C.DELETE_CHAR),
            "delete line, to line end, character",
        ),
        ((C.CHANGE_LINE, C.CHANGE_TO_LINE_END), "change line / to line end"),
        ((C.INDENT_LINE, C.UNINDENT_LINE), "nest / unnest the line"),
        ((C.REPLACE_CHAR,), "replace a character"),
        ((C.YANK_LINE,), "yank the line"),
        ((C.UNDO, C.REDO), "undo / redo"),
        # Search and replace
        ((C.SEARCH,), "search"),
        ((C.SEARCH_WORD,), "search for the word under the cursor"),
        ((M.SEARCH_NEXT, M.SEARCH_PREVIOUS), "next / previous match"),
        ((C.REPLACE_MATCHES,), "replace every match"),
        ((M.VIM_FLASH,), "flash: jump to text on screen"),
        ((C.PASTE_AFTER, C.PASTE_BEFORE), "paste after / before"),
    ),
    MODE_INSERT: (
        (("escape",), "back to NORMAL"),
        (("enter",), "new line, carrying on a list or quote"),
        ((editor_keys("indent"), editor_keys("dedent")), "nest / unnest the line"),
        ((editor_keys("paste"),), "paste, or attach a copied file"),
        ((editor_keys("select_all"),), "select all"),
        ((editor_keys("clear_note"),), "clear the whole note"),
    ),
    VISUAL_SECTION: (
        ((C.VISUAL, C.VISUAL_LINE), "start VISUAL / V-LINE; again to leave"),
        ((M.LEFT, M.RIGHT, M.UP, M.DOWN), "extend the selection, as any motion does"),
        ((T.INNER_WORD, T.INNER_PARAGRAPH), "select a text object"),
        ((C.OPEN_BELOW,), "go to the other end"),
        ((Op.YANK, Op.DELETE, Op.CHANGE), "yank, delete, change the selection"),
        ((Op.INDENT, Op.UNINDENT), "nest / unnest the selected lines"),
        ((C.PASTE_AFTER, C.PASTE_BEFORE), "replace with the register / keep it"),
        (("escape",), "back to NORMAL"),
    ),
    MODE_FLASH: (
        (
            (M.VIM_FLASH,),
            "start: type what to jump to; after an operator, takes up to it",
        ),
        ((flash_labels,), "a label jumps to its match"),
        (("enter",), "jump to the nearest match"),
        (("escape",), "cancel"),
    ),
    NOTE_WINDOW: (
        ((C.PICK_FILES,), "go to the attached files"),
        ((strip_moves,), "pick a file"),
        (("enter",), "open the file"),
        (("xx",), "detach the file"),
        ((C.OPEN_LINK,), "open the link under the cursor"),
        (("escape",), "close the note, from NORMAL"),
        ((C.HELP,), "this help"),
    ),
}

# Which mode's color each heading wears; the window's own wears the title's
SECTION_MODES = {
    MODE_NORMAL: MODE_NORMAL,
    MODE_INSERT: MODE_INSERT,
    VISUAL_SECTION: MODE_VISUAL,
    MODE_FLASH: MODE_FLASH,
}


def key_label(key: str) -> str:
    """A key as the help writes it: `<ctrl+u>` as `ctrl+u`, ` ?` as `space ?`."""

    if len(key) > 1 and " " in key:
        return " ".join("space" if char == " " else char for char in key)

    return TodooitKeyTable.key_label(key)


def row_keys(api: "TodooitAPI", parts: Sequence[Part]) -> Optional[str]:
    """A row's key column, or None if one of its actions has no key."""

    labels = []

    for part in parts:
        if isinstance(part, str):
            labels.append(key_label(part))
        elif callable(part):
            labels.append(part(api))
        elif (key := api.vim.keys.key_for(part)) is not None:
            labels.append(key_label(key))
        else:
            return None

    return "/".join(labels)


class NoteKeyTable(TodooitKeyTable):
    """The note's keys, section by section, each heading in its mode's color."""

    def __init__(self, api: "TodooitAPI") -> None:
        super().__init__(api.keys)
        self.api = api

    def _groups(self) -> List[str]:
        return list(SECTIONS)

    def _rows(self, group: str) -> List[Tuple[str, str]]:
        return [
            (keys, description)
            for parts, description in SECTIONS[group]
            if (keys := row_keys(self.api, parts)) is not None
        ]

    def _title_style(self, group: str) -> Style:
        theme = self.api.vars.theme
        mode = SECTION_MODES.get(group)
        color = getattr(theme, MODE_COLORS[mode]) if mode else theme.primary

        return Style(color=theme.background1, bgcolor=color, bold=True)


class NoteHelpScreen(HelpScreen):
    """The app's help, with the note's keys in it: scrolled by the note's own."""

    panel_title = PANEL_TITLE

    # The keys of the help's own binding typed so far, which close it again
    _typed = ""

    def compose(self) -> ComposeResult:
        with VerticalScroll(id="help-panel", can_focus=False):
            yield NoteKeyTable(self.api)

        keys = self.api.vim.keys
        up, down = (key_label(keys.key_for(motion) or "") for motion in (M.UP, M.DOWN))
        yield Static(hint(up, down), id="help-hint")

    def scrolls(self) -> Dict[str, str]:
        keys = self.api.vim.keys
        own = {
            keys.key_for(motion): scroll
            for motion, scroll in (
                (M.UP, "scroll_up"),
                (M.DOWN, "scroll_down"),
                (M.LEFT, "scroll_left"),
                (M.RIGHT, "scroll_right"),
            )
        }

        return {**self.SCROLLS, **{key: scroll for key, scroll in own.items() if key}}

    async def handle_key(self, event: events.Key) -> bool:
        # Its own keys close it again, as escape does
        key = self.resolve_key(event)
        typed = self._typed + (key if len(key) == 1 else f"<{key}>")
        own = self.api.vim.keys.keys_for(C.HELP)
        self._typed = ""

        if typed in own:
            event.stop()
            self.dismiss()
            return True

        if any(bound.startswith(typed) for bound in own):
            event.stop()
            self._typed = typed
            return True

        return await super().handle_key(event)
