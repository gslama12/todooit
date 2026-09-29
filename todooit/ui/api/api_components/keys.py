from enum import Enum
from dataclasses import dataclass
from collections import defaultdict
from typing import Callable, List, Literal, Optional, Tuple, Union

from ._base import ApiComponent
from todooit.ui.api.events import ModeType

KeyBindType = defaultdict[str, defaultdict[str, Optional["TodooitFunction"]]]
KeyType = Union[str, List[str]]

# Which pane a binding is meant for. A binding with no scope works over either
# of them; a scoped one is invisible everywhere else, which is what lets the
# same key be a key of its own over one pane and the opening of a chord over
# the other.
KeyScopeType = Literal["projects", "todos"]


@dataclass
class TodooitFunction:
    callback: Callable
    description: str = ""
    group: str = ""
    # Bindings obvious enough that a row in the help screen is just noise.
    # They still work; they are only left out of the listing, and a group
    # whose every binding is hidden drops out of the help screen entirely.
    hidden: bool = False
    # What the help screen writes in the key column instead of the key itself.
    # A run of keys that only differ in the digit at the end — p1, p2, p3 —
    # is a scale rather than four bindings, and reads as one row saying so;
    # every binding sharing a label and a description is listed once.
    label: str = ""
    # The pane the binding belongs to, or None for one that works over both
    scope: Optional[KeyScopeType] = None

    def __post_init__(self):
        self.description = self.description.strip("\n")


class KeyMatchType(Enum):
    NoMatchFound = "NoMatchFound"
    MultipleMatchFound = "MultipleMatchFound"
    MatchFound = "MatchFound"


@dataclass
class KeyMatch:
    match_type: KeyMatchType
    function: Optional[TodooitFunction] = None

    @staticmethod
    def no_match():
        return KeyMatch(match_type=KeyMatchType.NoMatchFound)

    @staticmethod
    def multiple_match():
        return KeyMatch(match_type=KeyMatchType.MultipleMatchFound)

    @staticmethod
    def match_found(func: TodooitFunction):
        return KeyMatch(match_type=KeyMatchType.MatchFound, function=func)


class KeyManager(ApiComponent):
    def __init__(self, get_mode: Callable, get_scope: Callable) -> None:
        self.keybinds: KeyBindType = defaultdict(lambda: defaultdict(lambda: None))
        self._inputs: List[str] = []
        self.get_mode = get_mode
        self.get_scope = get_scope

    @property
    def groups(self) -> List[str]:
        # Registration order, not alphabetical: the help screen shows the
        # groups in the order the config defines them
        groups = []
        for func in self.keybinds["NORMAL"].values():
            if func and not func.hidden and func.group not in groups:
                groups.append(func.group)

        return groups

    def get_keybinds_by_group(self, group: str) -> List[Tuple[str, TodooitFunction]]:
        return [
            (key, func)
            for key, func in self.keybinds["NORMAL"].items()
            if func and not func.hidden and func.group == group
        ]

    def __set_key(
        self,
        mode: ModeType,
        key: str,
        callback: Callable,
        description: Optional[str],
        group: str,
        hidden: bool,
        label: str,
        scope: Optional[KeyScopeType],
    ) -> None:
        self.keybinds[mode][key] = TodooitFunction(
            callback, description or callback.__doc__ or "", group, hidden, label, scope
        )

    def set(
        self,
        keys: KeyType,
        callback: Callable,
        description: Optional[str] = None,
        group: str = "",
        hidden: bool = False,
        label: str = "",
        scope: Optional[KeyScopeType] = None,
    ) -> None:
        if isinstance(keys, str):
            keys = [keys]

        for key in keys:
            self.__set_key(
                "NORMAL", key, callback, description, group, hidden, label, scope
            )

    @property
    def input(self) -> str:
        formatted = ""
        for i in self._inputs:
            if len(i) > 1:
                formatted += f"<{i}>"
            else:
                formatted += i

        return formatted

    def clear_input(self):
        self._inputs.clear()

    def _in_scope(self, func: TodooitFunction) -> bool:
        """
        Whether a binding is one the pane under the cursor answers to

        A binding that names no pane answers everywhere. A pane that is not one
        of the two -- nothing focused yet, or something that is not a tree --
        hears only those, since a chord that is being typed over nothing has no
        pane to be told apart from.
        """

        return func.scope is None or func.scope == self.get_scope()

    def _find_matched_functions(self) -> List[TodooitFunction]:
        keybinds = self.keybinds[self.get_mode()].items()
        return [
            func
            for key, func in keybinds
            if key.startswith(self.input) and func and self._in_scope(func)
        ]

    def _exact_match(self) -> Optional[TodooitFunction]:
        """
        The binding for exactly what has been typed so far, if the pane has one
        """

        func = self.keybinds[self.get_mode()].get(self.input)

        if func is None or not self._in_scope(func):
            return None

        return func

    def search_for_key(self) -> KeyMatch:
        matched = self._find_matched_functions()
        if not matched:
            self.clear_input()
            return KeyMatch.no_match()

        exact = self._exact_match()

        # Something longer than what was typed still matches, so the chord is
        # not finished: what has been typed waits for the key that ends it
        if len(matched) > 1 or exact is None:
            return KeyMatch.multiple_match()

        self.clear_input()
        return KeyMatch.match_found(exact)

    def register_key(self, key: str) -> KeyMatch:
        if key == "escape":
            self.clear_input()
            return KeyMatch.no_match()

        self._inputs.append(key)
        return self.search_for_key()
