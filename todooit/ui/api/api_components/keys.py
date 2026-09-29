from enum import Enum
from dataclasses import dataclass
from collections import defaultdict
from typing import Callable, List, Literal, Optional, Tuple, Union

from ._base import ApiComponent
from todooit.ui.api.events import ModeType

KeyBindType = defaultdict[str, defaultdict[str, Optional["TodooitFunction"]]]
KeyType = Union[str, List[str]]

# Which pane a binding applies to. Unscoped works over both; a scoped binding
# is invisible elsewhere, letting the same key mean different things per pane.
KeyScopeType = Literal["projects", "todos"]


@dataclass
class TodooitFunction:
    callback: Callable
    description: str = ""
    group: str = ""
    # Still works, just left out of the help screen listing (as noise); a
    # group with every binding hidden drops out entirely.
    hidden: bool = False
    # Key column text shown instead of the key itself, e.g. so p1/p2/p3 can
    # be listed as one row ("label") instead of three.
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
        # Registration order, not alphabetical, to match the config's order.
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
        Whether a binding applies to the currently focused pane. Unscoped
        bindings always match; with nothing (or a non-tree) focused, only
        those match.
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
        """The binding for exactly what has been typed so far, if any."""

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

        # A longer binding still matches, so the chord isn't finished yet.
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
