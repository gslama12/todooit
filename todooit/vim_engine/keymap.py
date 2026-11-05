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


class VimCommand(Enum):
    """Commands that do anything else."""

    INSERT = "insert"


VimAction = Union[VimMotion, VimCommand]


class VimKeymap:
    """
    Bindings from keys to commands. A binding can take several keys in a row
    (`dd`); a key with a name rather than a character goes in angle brackets
    (`<ctrl+u>`), as in `api.keys`.
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
