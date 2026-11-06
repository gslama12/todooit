"""
What the editor needs from the window it's in, so it never imports that window
"""

from typing import Iterable, Protocol, Union, runtime_checkable

from textual import events
from textual.content import Content


@runtime_checkable
class EditorHost(Protocol):
    @property
    def awaiting_answer(self) -> bool:
        """Whether a y/N question is up, waiting for the next keystroke."""

    def answer(self, key: str) -> None:
        """Answer the question that's up."""

    def attach(self, paths: Iterable[str]) -> None:
        """Attach pasted files to the note."""

    def mode_changed(self) -> None:
        """The keyboard mode changed: redraw whatever shows it."""

    def pending_changed(self) -> None:
        """The keys of a partial command changed: redraw whatever shows them."""

    def prompt_changed(self) -> None:
        """The search prompt opened, changed or closed: redraw whatever shows it."""

    def open_link(self, url: str) -> None:
        """Open `url`, reporting the outcome."""

    def pick_files(self) -> None:
        """Hand the keyboard to the note's attached files."""

    def report(self, message: Union[str, Content]) -> None:
        """Show the user a short message, which is markup if it's a string."""

    def request_clear(self) -> None:
        """Ask whether to clear the whole note, and do so on a yes."""

    def resolve_key(self, event: events.Key) -> str:
        """The key `event` stands for, resolved through the keyboard layout."""
