from typing import TYPE_CHECKING
from textual.app import events
from textual.screen import Screen

if TYPE_CHECKING:  # pragma: no cover
    from ..api import TodooitAPI
    from ..tui import Todooit


def cmd_as_ctrl(key: str) -> str:
    """
    The ctrl twin of a Cmd chord (`super+c` -> `ctrl+c`), so every ctrl
    shortcut also answers to Cmd on a Mac. Anything else, including a chord
    already holding ctrl, comes back unchanged.
    """

    *modifiers, name = key.split("+")

    if "super" not in modifiers or "ctrl" in modifiers:
        return key

    # Sorted, as Textual writes modifiers: cmd+shift+left is ctrl+shift+left
    modifiers = sorted("ctrl" if m == "super" else m for m in modifiers)

    return "+".join([*modifiers, name])


class BaseScreen(Screen, inherit_bindings=False):
    """Base screen with a helper to resolve a `Key` event to a str."""

    SPACE_CHARACTERS = (
        "\u0020\u00a0\u1680\u202f\u205f\u3000"
        "\u2002\u2003\u2004\u2005\u2006\u2007\u2008\u2009\u200a\u200b"
    )

    @property
    def app(self) -> "Todooit":
        from ..tui import Todooit

        app = super().app
        assert isinstance(app, Todooit)

        return app

    @property
    def api(self) -> "TodooitAPI":
        return self.app.api

    def resolve_key(self, event: events.Key) -> str:
        # Checked before the character: a terminal may send a Cmd chord with
        # its letter attached, which would otherwise be typed as that letter.
        if (key := cmd_as_ctrl(event.key)) != event.key:
            return key

        if not event.character:
            return event.key

        if event.is_printable or event.character in self.SPACE_CHARACTERS:
            return event.character

        return event.key
