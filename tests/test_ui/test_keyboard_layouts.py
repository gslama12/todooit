"""
Keyboard layouts: bindings moved onto other keys, and the shipped vim configs

The overlays (calendar, note, help, attachment strip) take their direction
keys from the panes' bindings, so a config that moves the pane keys moves
those too without touching anything else.
"""

import importlib.util
from datetime import date, timedelta
from pathlib import Path

import pytest

from tests.test_ui.test_calendar import a_todo_being_dated
from tests.test_ui.test_note_ui import open_note
from tests.test_ui.ui_base import boot, run_pilot
from todooit.ui.api.api_components.keys import MotionKeys
from todooit.ui.screens import HelpScreen
from todooit.ui.screens.note.vim.modes import MODE_NORMAL
from todooit.ui.widgets.trees import ProjectsTree, TodosTree

CONFIG_DIR = Path(__file__).parents[2] / "config"

# Config file -> the key its fold/unfold lands on
LAYOUTS = {"qwertz_vim.py": "ö", "qwerty_vim.py": ";"}


def apply_layout(api, name: str) -> None:
    """Runs a shipped config's Startup handler, as loading it would"""

    path = CONFIG_DIR / name
    spec = importlib.util.spec_from_file_location(f"layout_{path.stem}", path)
    assert spec and spec.loader
    module = importlib.util.module_from_spec(spec)
    spec.loader.exec_module(module)

    module.vim_keys(api, None)


async def test_remap_moves_bindings_and_keeps_their_place():
    async with run_pilot() as pilot:
        app = await boot(pilot)
        keys = app.api.keys
        binds = keys.keybinds["NORMAL"]
        order = list(binds)
        before = {key: binds[key] for key in ("j", "l", "h")}

        # A rotation: every target is a key that is itself moved away
        moves = {"j": "l", "l": "h", "h": "j"}
        keys.remap(moves)

        assert binds["l"] is before["j"]
        assert binds["h"] is before["l"]
        assert binds["j"] is before["h"]
        # Same slots in the help screen, under the new names
        assert list(binds) == [moves.get(key, key) for key in order]


async def test_remap_refuses_to_overwrite_or_invent():
    async with run_pilot() as pilot:
        app = await boot(pilot)
        keys = app.api.keys
        snapshot = dict(keys.keybinds["NORMAL"])

        # `k` is still bound to moving up and isn't moved away
        with pytest.raises(ValueError):
            keys.remap({"j": "k"})

        # Two bindings can't share one key
        with pytest.raises(ValueError):
            keys.remap({"j": "Q", "l": "Q"})

        with pytest.raises(KeyError):
            keys.remap({"Q": "j"})

        # A refused remap changes nothing
        assert dict(keys.keybinds["NORMAL"]) == snapshot


async def test_motion_keys_follow_the_pane_bindings():
    async with run_pilot() as pilot:
        app = await boot(pilot)
        api = app.api

        assert api.motion_keys() == MotionKeys("j", "ö", "k", "l")

        # Nothing single-key left to move up with: the arrow stands in
        api.keys.remap({"k": "<f8>"})
        assert api.motion_keys().up == "up"


@pytest.mark.parametrize("layout", LAYOUTS)
async def test_vim_layout_moves_the_panes(layout):
    async with run_pilot() as pilot:
        app = await boot(pilot)
        api = app.api
        apply_layout(api, layout)

        assert api.motion_keys() == MotionKeys("h", "l", "k", "j")

        binds = api.keys.keybinds["NORMAL"]
        assert binds[LAYOUTS[layout]].callback == api.toggle_expand
        assert binds["J"].callback == api.shift_down
        assert binds["K"].callback == api.shift_up
        if layout == "qwerty_vim.py":
            assert binds.get("ö") is None
        assert binds.get("L") is None

        await pilot.press("h")
        await pilot.pause()
        assert isinstance(app.focused, ProjectsTree)

        await pilot.press("l")
        await pilot.pause()
        assert isinstance(app.focused, TodosTree)


@pytest.mark.parametrize("layout", LAYOUTS)
async def test_vim_layout_walks_the_calendar(layout):
    async with run_pilot() as pilot:
        app = await boot(pilot)
        # The helper drives the panes with the default keys; the calendar
        # reads the direction keys at each press, so switching here is enough
        screen = await a_todo_being_dated(pilot)
        apply_layout(app.api, layout)
        today = date.today()

        await pilot.press("l")
        assert screen._selected == today + timedelta(days=1)

        await pilot.press("j")
        assert screen._selected == today + timedelta(days=8)

        await pilot.press("k", "h")
        assert screen._selected == today

        # The shifted direction keys walk whole months
        await pilot.press("L")
        assert screen._selected.month == today.month % 12 + 1
        await pilot.press("H")
        assert screen._selected.month == today.month


async def test_vim_layout_moves_the_note_cursor():
    async with run_pilot() as pilot:
        app = await boot(pilot)
        screen = await open_note(pilot)
        apply_layout(app.api, "qwerty_vim.py")
        editor = screen.editor

        await pilot.press(*"ab")
        await pilot.press("enter")
        await pilot.press(*"cd")
        await pilot.press("escape")
        await pilot.pause()
        assert editor.mode == MODE_NORMAL
        assert "hl/kj move" in str(screen.hint.render())

        start = editor.cursor_location
        await pilot.press("k")
        assert editor.cursor_location[0] == start[0] - 1
        await pilot.press("j")
        assert editor.cursor_location[0] == start[0]

        await pilot.press("h")
        assert editor.cursor_location[1] == start[1] - 1
        await pilot.press("l")
        assert editor.cursor_location == start


async def test_vim_layout_scrolls_the_help():
    async with run_pilot() as pilot:
        app = await boot(pilot)
        apply_layout(app.api, "qwertz_vim.py")

        await pilot.press("?")
        await pilot.pause()
        screen = app.screen
        assert isinstance(screen, HelpScreen)

        scrolls = screen.scrolls()
        assert scrolls["j"] == "scroll_down"
        assert scrolls["k"] == "scroll_up"
        assert scrolls["h"] == "scroll_left"
        assert scrolls["l"] == "scroll_right"
        assert "ö" not in scrolls
