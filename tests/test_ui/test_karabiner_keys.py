"""
The Karabiner Esc layer, typed into todooit through WezTerm

Holding Esc turns the right hand into macOS text-editing chords (cmd/opt +
arrows, and so on), and WezTerm turns each chord into what a terminal program
can read. These tests start from the bytes WezTerm sends while todooit is in
front (see the WezTerm config in the installation guide), run them through
Textual's own parser, and check that every layer key does in a text field
and in the note editor what it does in any other Mac app.

The one that needs care is Esc+u: at a zsh prompt WezTerm sends it as ^A,
but in todooit ^A is `ctrl+a`, the same key as `cmd+a`: select all. So in
todooit WezTerm has to send it as Home instead.
"""

from typing import List, Optional, Tuple

import pytest
from textual._xterm_parser import XTermParser
from textual.pilot import Pilot

from tests.test_ui.test_note_ui import open_note
from tests.test_ui.ui_base import (
    commit_line,
    create_and_move_to_todo,
    run_pilot,
)
from todooit.ui.screens.note.vim.editor import NoteEditor
from todooit.ui.widgets.inputs._input import Input

# What WezTerm sends into todooit for each Esc-layer key
WEZTERM = {
    "j": "\x1b[D",  # left
    "ö": "\x1b[C",  # right
    "u": "\x1b[H",  # cmd+left -> Home (^A would select all)
    "i": "\x1b[F",  # cmd+right -> End
    "m": "\x1bb",  # opt+left -> ESC b
    ",": "\x1bf",  # opt+right -> ESC f
    "c": "\x1b\x7f",  # opt+backspace -> ESC DEL
    "backspace": "\x1b\x7f",
    "v": "\x1bd",  # opt+delete -> ESC d
    "x": "\x15",  # ctrl+u
    "g": "\x1b[3~",  # delete
    "h": "\x7f",  # backspace
    "d": "\x1b[1;2D",  # shift+left
    "f": "\x1b[1;2C",  # shift+right
    "e": "\x1b[1;4D",  # shift+opt+left
    "r": "\x1b[1;4C",  # shift+opt+right
    "t": "\x1b[H\x1b[1;2F",  # cmd+left, then cmd+shift+right -> shift+End
    "y": "\x1b[1;5H",  # cmd+up -> ctrl+Home
    "n": "\x1b[1;5F",  # cmd+down -> ctrl+End
}

TEXT = "one two three"


async def type_layer_key(pilot: Pilot, layer_key: str) -> None:
    """
    Types one Esc-layer key as the terminal would: the parser's own events,
    character and all (`ESC d` is `alt+d` *with* a `d`, which a key name alone
    would not reproduce)
    """

    parser = XTermParser()

    for event in [*parser.feed(WEZTERM[layer_key]), *parser.feed("")]:
        pilot.app.post_message(event)
        await pilot.pause()


# layer key, cursor before, (text, cursor, selection) after
FIELD_CASES: List[Tuple[str, int, Tuple[str, int, Optional[Tuple[int, int]]]]] = [
    ("j", 13, (TEXT, 12, None)),
    ("ö", 0, (TEXT, 1, None)),
    ("u", 13, (TEXT, 0, None)),
    ("i", 0, (TEXT, 13, None)),
    ("m", 13, (TEXT, 8, None)),
    (",", 0, (TEXT, 4, None)),
    ("c", 13, ("one two ", 8, None)),
    ("backspace", 13, ("one two ", 8, None)),
    ("v", 4, ("one three", 4, None)),
    ("x", 6, ("", 0, None)),
    ("g", 0, ("ne two three", 0, None)),
    ("h", 13, ("one two thre", 12, None)),
    ("d", 13, (TEXT, 12, (12, 13))),
    ("f", 0, (TEXT, 1, (0, 1))),
    ("e", 13, (TEXT, 8, (8, 13))),
    ("r", 0, (TEXT, 4, (0, 4))),
    ("t", 6, (TEXT, 13, (0, 13))),
    ("y", 6, (TEXT, 0, None)),
    ("n", 6, (TEXT, 13, None)),
]


async def editing_field(pilot: Pilot, cursor: int) -> Input:
    """A task named TEXT, its description open for editing, cursor placed"""

    tree = await create_and_move_to_todo(pilot)
    await pilot.press("n")
    await commit_line(pilot, TEXT)

    await pilot.press("i")
    await pilot.pause()

    field = tree.current._get_component(tree.current.editing)
    field._selection_anchor = None
    field._cursor_position = cursor

    return field


@pytest.mark.parametrize("layer_key, cursor, after", FIELD_CASES)
async def test_the_esc_layer_in_a_text_field(layer_key, cursor, after):
    async with run_pilot() as pilot:
        field = await editing_field(pilot, cursor)

        await type_layer_key(pilot, layer_key)

        assert (field.value, field.cursor_position, field.selection) == after


async def test_ctrl_a_still_selects_all_in_a_text_field():
    # why WezTerm must not send Esc+u to todooit as ^A
    async with run_pilot() as pilot:
        field = await editing_field(pilot, 6)

        await pilot.press("super+a")
        await pilot.pause()

        assert field.selection == (0, len(TEXT))


LINE = f"above\n{TEXT}\nbelow"

# layer key, column before on the middle line, (text, cursor, selected) after
NOTE_CASES = [
    ("j", 13, (LINE, (1, 12), "")),
    ("ö", 0, (LINE, (1, 1), "")),
    ("u", 13, (LINE, (1, 0), "")),
    ("i", 0, (LINE, (1, 13), "")),
    ("m", 13, (LINE, (1, 8), "")),
    (",", 0, (LINE, (1, 3), "")),
    ("c", 13, ("above\none two \nbelow", (1, 8), "")),
    ("backspace", 13, ("above\none two \nbelow", (1, 8), "")),
    ("v", 4, ("above\none  three\nbelow", (1, 4), "")),
    ("x", 6, ("above\n\nbelow", (1, 0), "")),
    ("g", 0, ("above\nne two three\nbelow", (1, 0), "")),
    ("h", 13, ("above\none two thre\nbelow", (1, 12), "")),
    ("d", 13, (LINE, (1, 12), "e")),
    ("f", 0, (LINE, (1, 1), "o")),
    ("e", 13, (LINE, (1, 8), "three")),
    ("r", 0, (LINE, (1, 3), "one")),
    ("t", 6, (LINE, (1, 13), TEXT)),
    ("y", 6, (LINE, (0, 0), "")),
    ("n", 6, (LINE, (2, 5), "")),
]


@pytest.mark.parametrize("layer_key, column, after", NOTE_CASES)
async def test_the_esc_layer_in_the_note_editor(layer_key, column, after):
    async with run_pilot() as pilot:
        await open_note(pilot)
        editor = pilot.app.screen.query_one(NoteEditor)

        # an empty note opens in INSERT, where the layer keys edit
        editor.insert(LINE)
        editor.move_cursor((1, column))
        await pilot.pause()

        await type_layer_key(pilot, layer_key)

        assert (editor.text, editor.cursor_location, editor.selected_text) == after


async def test_the_esc_layer_jumps_to_the_top_and_bottom_of_a_list():
    async with run_pilot() as pilot:
        tree = await create_and_move_to_todo(pilot)

        for name in ("first", "second", "third"):
            await pilot.press("n")
            await commit_line(pilot, name)

        await type_layer_key(pilot, "y")
        assert tree.current_model.description == "first"

        await type_layer_key(pilot, "n")
        assert tree.current_model.description == "third"
