"""
The one register, and how it stands to the system clipboard
"""

from dataclasses import dataclass
from typing import Callable, Optional, Tuple


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
    # yank, or what was there at the last delete or when the first note opened.
    # None until then.
    known_clipboard: Optional[str] = None

    # Gives what was there at the last delete, until a paste first asks
    _clipboard_then: Optional[Callable[[], str]] = None

    def keep_yanked(self, register: Register) -> None:
        """Keep what was yanked, which is on the system clipboard too."""

        self.register = register
        self.know_clipboard(register.text)

    def keep_deleted(
        self, register: Register, clipboard_then: Callable[[], str]
    ) -> None:
        """
        Keep what was deleted or changed. It's newer than whatever the system
        clipboard holds by now, which `clipboard_then` gives once it's known.
        """

        self.register = register
        self._clipboard_then = clipboard_then

    def know_clipboard(self, text: str) -> None:
        """The system clipboard holds `text`, and that's no news any more."""

        self.known_clipboard = text
        self._clipboard_then = None

    def pastes_clipboard(self, text: str) -> bool:
        """Whether a paste should take `text` off the clipboard over the register."""

        if self._clipboard_then is not None:
            self.know_clipboard(self._clipboard_then())

        if not text:
            return False

        if self.register is None or self.known_clipboard is None:
            return True

        return _even_line_breaks(text) != _even_line_breaks(self.known_clipboard)
