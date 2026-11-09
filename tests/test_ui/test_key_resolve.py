import pytest
from textual import events

from tests.test_ui.ui_base import boot, run_pilot
from todooit.ui.screens import MainScreen
from todooit.ui.screens.base import cmd_as_ctrl


async def test_base_screen_keys():
    async with run_pilot() as pilot:
        # `pause` alone is not enough: the main screen is pushed from
        # `on_mount`, so a test that looks at `app.screen` before the app has
        # settled can find nothing on the stack at all
        app = await boot(pilot)
        screen = app.screen

        assert isinstance(screen, MainScreen)

        assert screen.resolve_key(events.Key("home", None)) == "home"
        assert screen.resolve_key(events.Key("space", " ")) == " "

        # Cmd is read as ctrl, even when the terminal sends its letter along
        assert screen.resolve_key(events.Key("super+c", None)) == "ctrl+c"
        assert screen.resolve_key(events.Key("super+c", "c")) == "ctrl+c"


@pytest.mark.parametrize(
    "key, expected",
    [
        ("super+c", "ctrl+c"),
        ("super+q", "ctrl+q"),
        ("shift+super+left", "ctrl+shift+left"),
        ("alt+super+x", "alt+ctrl+x"),
        # Not a Cmd chord: left alone
        ("ctrl+c", "ctrl+c"),
        ("c", "c"),
        ("plus", "plus"),
        # Already holding ctrl, so there is no ctrl twin to turn into
        ("ctrl+super+c", "ctrl+super+c"),
    ],
)
def test_cmd_as_ctrl(key, expected):
    assert cmd_as_ctrl(key) == expected
