"""
The one register, and how it stands to the system clipboard
"""

from dataclasses import dataclass
from typing import Optional, Tuple


@dataclass(frozen=True)
class Register:
    """What was last yanked or deleted, and whether it was whole lines."""

    text: str
    linewise: bool

    # Whether it came off the system clipboard, so it pastes the way that does
    from_clipboard: bool = False


@dataclass(frozen=True)
class YankedRange:
    """
    What the last key yanked, from a place up to, not including, another; for
    a host to flash. Whole lines run from the first's start to the last's end.
    """

    start: Tuple[int, int]
    end: Tuple[int, int]
    linewise: bool


def _even_line_breaks(text: str) -> str:
    """Text as any clipboard hands it back: some change its line breaks."""

    return text.replace("\r\n", "\n").rstrip("\n")


@dataclass
class RegisterMemory:
    """The register, kept by whoever outlives a single engine."""

    register: Optional[Register] = None

    # What the system clipboard last held that a paste shouldn't prefer: the last
    # yank, or what was there when the first note opened. None until then.
    known_clipboard: Optional[str] = None

    def pastes_clipboard(self, text: str) -> bool:
        """Whether a paste should take `text` off the clipboard over the register."""

        if not text:
            return False

        if self.register is None or self.known_clipboard is None:
            return True

        return _even_line_breaks(text) != _even_line_breaks(self.known_clipboard)
