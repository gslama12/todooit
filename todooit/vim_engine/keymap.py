"""
Which keys mean what, in the style of `api.keys`
"""

from enum import Enum
from typing import Dict, List, Optional, Union


class VimMotion(Enum):
    """Commands that move the cursor."""

    LEFT = "left"
    RIGHT = "right"
    UP = "up"
    DOWN = "down"
    WORD_FORWARD = "word_forward"
    WORD_BACKWARD = "word_backward"
    WORD_END = "word_end"
    FIRST_NON_BLANK = "first_non_blank"
    LAST_CHARACTER = "last_character"
    LINE_ABOVE = "line_above"
    LINE_BELOW = "line_below"
    FIND_FORWARD = "find_forward"
    FIND_BACKWARD = "find_backward"
    TILL_FORWARD = "till_forward"
    TILL_BACKWARD = "till_backward"
    REPEAT_FIND = "repeat_find"
    REVERSE_FIND = "reverse_find"
    HALF_PAGE_UP = "half_page_up"
    HALF_PAGE_DOWN = "half_page_down"
    TOP = "top"
    BOTTOM = "bottom"
    PARAGRAPH_UP = "paragraph_up"
    PARAGRAPH_DOWN = "paragraph_down"
    SEARCH_NEXT = "search_next"
    SEARCH_PREVIOUS = "search_previous"


class VimCommand(Enum):
    """Commands that do anything else."""

    INSERT = "insert"
    INSERT_AFTER = "insert_after"
    INSERT_FIRST_NON_BLANK = "insert_first_non_blank"
    INSERT_LINE_END = "insert_line_end"
    INSERT_AT_LAST = "insert_at_last"
    OPEN_BELOW = "open_below"
    OPEN_ABOVE = "open_above"
    CENTER_VIEW = "center_view"
    OPEN_LINK = "open_link"
    PICK_FILES = "pick_files"
    DELETE_LINE = "delete_line"
    DELETE_TO_LINE_END = "delete_to_line_end"
    DELETE_CHAR = "delete_char"
    CHANGE_LINE = "change_line"
    CHANGE_TO_LINE_END = "change_to_line_end"
    REPLACE_CHAR = "replace_char"
    UNDO = "undo"
    REDO = "redo"
    SEARCH = "search"
    SEARCH_WORD = "search_word"


class VimOperator(Enum):
    """Commands that act on the text a motion goes over."""

    DELETE = "delete"
    CHANGE = "change"


VimAction = Union[VimMotion, VimCommand, VimOperator]


class VimKeymap:
    """
    Bindings from keys to commands. A binding can take several keys in a row
    (`dd`); a key with a name rather than a character goes in angle brackets
    (`<ctrl+u>`), as in `api.keys`.

    An operator's key wins over a longer binding starting with it: `d` is the
    operator, and `dd` is what its keys and the next key are looked up as first.
    """

    def __init__(self) -> None:
        self._bindings: Dict[str, VimAction] = {}

    def set(self, keys: Union[str, List[str]], action: VimAction) -> None:
        """Bind one key, or each of a list, to `action`."""

        for key in [keys] if isinstance(keys, str) else keys:
            self._bindings[key] = action

    def remap(self, moves: Dict[str, str]) -> None:
        """
        Move bindings onto other keys, `{old: new}`. All moves happen at once, so
        keys can be swapped or rotated; a new key that is still bound to something
        not moved away is an error, not a silent overwrite.
        """

        binds = self._bindings

        if unbound := [old for old in moves if old not in binds]:
            raise KeyError(f"Nothing is bound to {', '.join(unbound)}")

        targets = list(moves.values())
        taken = [
            new
            for new in targets
            if targets.count(new) > 1 or (new in binds and new not in moves)
        ]
        if taken:
            raise ValueError(f"Already bound: {', '.join(dict.fromkeys(taken))}")

        self._bindings = {moves.get(key, key): action for key, action in binds.items()}

    def action_for(self, keys: str) -> Optional[VimAction]:
        """What exactly these keys are bound to, if anything."""

        return self._bindings.get(keys)

    def continues(self, keys: str) -> bool:
        """Whether a longer binding starts with these keys."""

        return any(
            bound != keys and bound.startswith(keys) for bound in self._bindings
        )

    def key_for(self, action: VimAction) -> Optional[str]:
        """The first key bound to `action`, if any."""

        for key, bound in self._bindings.items():
            if bound == action:
                return key

        return None
