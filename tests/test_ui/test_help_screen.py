"""
The help screen: the keybinds of the config, grouped the way it groups them
"""

from todooit.ui.api.events import SpawnHelp
from todooit.ui.screens import HelpScreen, MainScreen
from todooit.ui.screens.help import DooitKeyTable
from tests.test_ui.ui_base import boot, run_pilot


async def test_help_screen_mount():
    async with run_pilot() as pilot:
        # Settled first: the startup jump to Today lands as a message, and one
        # arriving while the help screen is on top finds no projects pane to
        # move the cursor in
        app = await boot(pilot)

        app.api.keys.set("X", app.api.no_op)  # test cover no_op
        app.api.keys.set("Z", app.api.move_up, group="test")  # group test

        # test if help screen is mounted
        await app.push_screen("help")
        assert isinstance(app.screen, HelpScreen)

        await app.push_screen("main")

        # test with keybinding
        await pilot.press("?")
        assert isinstance(app.screen, HelpScreen)
        await app.push_screen("main")

        # test function
        assert isinstance(app.screen, MainScreen)
        await app.screen.spawn_help(SpawnHelp())
        assert isinstance(app.screen, HelpScreen)


async def test_help_lists_the_config_groups_in_order():
    async with run_pilot() as pilot:
        app = await boot(pilot)

        assert app.api.keys.groups == [
            "Navigation",
            "Editing",
            "Moving & Clipboard",
            "Search & View",
        ]


async def test_every_visible_keybind_has_a_row():
    async with run_pilot() as pilot:
        app = await boot(pilot)

        await app.push_screen("help")
        table = app.screen.query_one(DooitKeyTable)

        rows = {
            label: description
            for group in app.api.keys.groups
            for label, description in table._rows(group)
        }

        # A spot check across the groups: one key per feature family
        for label in ("j", "gt", "n", "C", "space", "xx", "YY", "/", "o", "q"):
            assert label in rows, label

        # The priority scale collapses to one row instead of four
        assert "p0-p3" in rows
        assert "p1" not in rows

        # The agent flag is one key rather than a scale, so it is its own row
        assert "a" in rows

        # So do the sort chords
        assert "SP/SD/SS" in rows
        assert "SP" not in rows

        # Named keys are written without their angle brackets
        assert "ctrl+q" in rows
        assert "ctrl+c" in rows


async def test_hidden_keybinds_stay_out_of_the_help():
    async with run_pilot() as pilot:
        app = await boot(pilot)

        await app.push_screen("help")
        table = app.screen.query_one(DooitKeyTable)

        labels = [
            label
            for group in app.api.keys.groups
            for label, _ in table._rows(group)
        ]

        # `?` itself is hidden: the key that opened the window is not news
        assert "?" not in labels


async def test_the_help_stays_open_until_escape():
    """
    `?` opens a window that stays, the way the note and the finder do

    It used to be a hold-to-show overlay that closed itself as soon as `?`
    stopped repeating, which left nothing to scroll a listing taller than the
    screen with: every key that would have moved it also ended it.
    """

    async with run_pilot() as pilot:
        app = await boot(pilot)

        await pilot.press("?")
        assert isinstance(app.screen, HelpScreen)

        # Nothing held down, and a scroll key pressed where the close timer
        # used to be waiting
        for _ in range(5):
            await pilot.pause()

        await pilot.press("l")
        await pilot.pause()
        assert isinstance(app.screen, HelpScreen)

        await pilot.press("escape")
        await pilot.pause()
        assert isinstance(app.screen, MainScreen)


async def test_help_scrolls_with_the_navigation_keys():
    async with run_pilot() as pilot:
        app = await boot(pilot)

        await pilot.press("?")
        await pilot.pause()

        screen = app.screen
        assert isinstance(screen, HelpScreen)

        # The listing is taller than the window it opens in; a test that
        # scrolls a window with nothing under the fold proves nothing
        assert screen.max_scroll_y > 0

        await pilot.press("l")
        await pilot.pause()
        assert screen.scroll_target_y > 0

        await pilot.press("k")
        await pilot.pause()
        assert screen.scroll_target_y == 0

        await pilot.press("G")
        await pilot.pause()
        assert screen.scroll_target_y == screen.max_scroll_y

        # One `g` on its own waits for the second rather than jumping
        await pilot.press("g")
        await pilot.pause()
        assert screen.scroll_target_y == screen.max_scroll_y

        await pilot.press("g")
        await pilot.pause()
        assert screen.scroll_target_y == 0
