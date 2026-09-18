from textual import events
from tests.test_ui.ui_base import boot, run_pilot
from todooit.ui.screens import MainScreen


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
