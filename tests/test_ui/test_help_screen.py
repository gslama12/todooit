"""
The help overlay: the keybinds of the config, grouped the way it groups them
"""

from textual.screen import ModalScreen

from tests.test_ui.ui_base import boot, run_pilot
from todooit.ui.screens import HelpScreen, MainScreen
from todooit.ui.screens.help import TodooitKeyTable


async def test_help_is_an_overlay_like_the_others():
    """
    Spawned fresh over the main screen, the way the note and the finder are,
    rather than switched to as a named screen of its own
    """

    async with run_pilot() as pilot:
        # Settled first: the startup jump to Today lands as a message, and one
        # arriving while the help is on top finds no projects pane to move
        # the cursor in
        app = await boot(pilot)

        assert "help" not in app.SCREENS

        # A keybind to a no-op and one in a group of its own both get a row
        app.api.keys.set("X", app.api.no_op)
        app.api.keys.set("Z", app.api.move_up, group="test")

        await pilot.press("?")
        await pilot.pause()

        first = app.screen
        assert isinstance(first, HelpScreen)
        assert isinstance(first, ModalScreen)
        assert first.panel.border_title == "Key Bindings"
        assert "Z" in dict(first.query_one(TodooitKeyTable)._rows("test"))

        # The panes stay behind it, dimmed rather than gone
        assert isinstance(app.screen_stack[-2], MainScreen)

        await pilot.press("escape")
        await pilot.pause()

        # Through the api this time, which is what the keybind calls
        app.api.show_help()
        await pilot.pause()
        assert isinstance(app.screen, HelpScreen)
        assert app.screen is not first


async def test_help_swallows_every_other_key():
    async with run_pilot() as pilot:
        app = await boot(pilot)
        main = app.screen

        await pilot.press("?")
        await pilot.pause()
        assert isinstance(app.screen, HelpScreen)

        # `?` does not toggle it shut, and keys that do something behind it
        # -- a new project, quitting -- reach nothing
        for key in ("?", "q", "a", "enter", "space"):
            await pilot.press(key)
            await pilot.pause()
            assert isinstance(app.screen, HelpScreen), key

        await pilot.press("escape")
        await pilot.pause()
        assert app.screen is main
        assert app.todooit_mode == "NORMAL"


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

        await pilot.press("?")
        await pilot.pause()
        table = app.screen.query_one(TodooitKeyTable)

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

        # So do the sort chords
        assert "SP/SD/SS" in rows
        assert "SP" not in rows

        # Named keys are written without their angle brackets
        assert "ctrl+c" in rows


async def test_hidden_keybinds_stay_out_of_the_help():
    async with run_pilot() as pilot:
        app = await boot(pilot)

        await pilot.press("?")
        await pilot.pause()
        table = app.screen.query_one(TodooitKeyTable)

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

        assert isinstance(app.screen, HelpScreen)
        # The panel scrolls, not the screen: the hint under it stays put
        screen = app.screen.panel

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
