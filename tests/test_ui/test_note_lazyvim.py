"""
The note window as LazyVim's: the line number gutter, the mode chip and border,
the yank flash, the help pane on Cmd+? and the optional hint line
"""

from typing import Callable, List, Tuple

import pytest
from textual.geometry import Offset

from tests.test_ui.test_keyboard_layouts import apply_layout
from tests.test_ui.test_note_ui import open_note
from tests.test_ui.test_vim_note import cell, drawn_row, note_of, theme_of
from tests.test_ui.ui_base import create_and_move_to_todo, run_pilot
from todooit.api import PinnedNote
from todooit.ui.screens.help import HelpScreen
from todooit.ui.screens.note import NoteScreenBase, PinnedNoteScreen
from todooit.ui.screens.note.disp.markup import GUTTER, GUTTER_CURSOR, YANKED
from todooit.ui.screens.note.screens.help import NoteHelpScreen, NoteKeyTable
from todooit.ui.screens.note.vim import modes
from todooit.vim_engine import (
    MODE_FLASH,
    MODE_INSERT,
    MODE_NORMAL,
    MODE_VISUAL,
    MODE_VISUAL_LINE,
    VimCommand,
    VimMotion,
)


def gutter(editor, y: int) -> str:
    """The line number drawn on a row of the window."""

    return editor.render_line(y).text[: editor.gutter_width]


def gutter_style(editor, y: int):
    return editor.render_line(y).crop(0, 1)._segments[0].style


# ------------------------------------------------------------------
# ------------------------- The gutter -----------------------------
# ------------------------------------------------------------------


async def test_the_cursor_line_shows_its_number_and_the_others_their_distance():
    async with run_pilot() as pilot:
        screen = await note_of(pilot, "a\nb\nc\nd", at=(1, 0))
        editor = screen.editor

        assert editor.gutter_width == 3
        assert [gutter(editor, y) for y in range(4)] == ["1  ", "2  ", "1  ", "2  "]

        await pilot.press("l", "l")
        await pilot.pause()

        assert [gutter(editor, y) for y in range(4)] == ["3  ", "2  ", "1  ", "4  "]


async def test_the_numbers_sit_close_to_the_frame_and_further_from_the_text():
    async with run_pilot() as pilot:
        screen = await note_of(pilot, "a\nb")
        editor = screen.editor
        row = gutter(editor, 0)

        before = screen.frame.styles.padding.left + len(row) - len(row.lstrip())
        after = len(row) - len(row.rstrip())

        assert (before, after) == (1, 2)


async def test_the_numbers_are_dim_and_the_cursor_lines_bold_orange_from_the_theme():
    async with run_pilot() as pilot:
        screen = await note_of(pilot, "a\nb", at=(0, 0))
        editor = screen.editor
        theme = pilot.app.api.vars.theme

        own = gutter_style(editor, 0)
        other = gutter_style(editor, 1)

        assert own.color == theme_of(editor)[GUTTER_CURSOR].color
        assert own.color.name.lower() == theme.orange.lower()
        assert own.bold
        assert other.color == theme_of(editor)[GUTTER].color
        assert not other.bold


async def test_a_wrapped_lines_other_rows_have_no_number_and_a_count_lands_where_it_says():
    async with run_pilot() as pilot:
        screen = await note_of(pilot, "word " * 40 + "\nsecond\nthird")
        editor = screen.editor

        # The first line takes several rows; only the first of them is numbered
        second = editor.wrapped_document.location_to_offset((1, 0)).y
        assert second > 1
        assert gutter(editor, 0) == "1  "
        assert all(gutter(editor, y).strip() == "" for y in range(1, second))
        assert gutter(editor, second) == "1  "
        assert gutter(editor, second + 1) == "2  "
        assert drawn_row(editor, second).startswith("second")

        # `2` + down goes by the numbers, not the rows drawn
        await pilot.press("2", "l")
        await pilot.pause()
        assert editor.cursor_location[0] == 2


async def test_the_gutter_grows_with_the_number_of_lines():
    async with run_pilot() as pilot:
        screen = await note_of(pilot, "\n".join("x" * 1200))
        editor = screen.editor

        assert editor.gutter_width == 6
        assert gutter(editor, 0) == "   1  "


async def test_the_numbers_follow_the_cursor_in_every_mode():
    async with run_pilot() as pilot:
        screen = await note_of(pilot, "abc\ndef\nghi", at=(0, 0))
        editor = screen.editor

        await pilot.press("v", "l")
        await pilot.pause()
        assert editor.mode == MODE_VISUAL
        assert gutter(editor, 1) == "2  "

        await pilot.press("escape", "V", "l")
        await pilot.pause()
        assert editor.mode == MODE_VISUAL_LINE
        assert gutter(editor, 2) == "3  "

        await pilot.press("escape", "s")
        await pilot.pause()
        assert editor.mode == MODE_FLASH
        assert gutter(editor, 2) == "3  "

        await pilot.press("escape", "o")
        await pilot.pause()
        assert editor.mode == MODE_INSERT
        assert gutter(editor, 3) == "4  "
        assert gutter(editor, 0) == "3  "


async def test_a_click_lands_on_the_character_after_the_gutter():
    async with run_pilot() as pilot:
        screen = await note_of(pilot, "abcdef\nghijkl")
        editor = screen.editor

        await pilot.click(editor, offset=Offset(editor.gutter_width + 3, 1))
        await pilot.pause()

        assert editor.cursor_location == (1, 3)


async def test_the_pinned_note_has_the_gutter_too():
    async with run_pilot() as pilot:
        PinnedNote.set_text("one\ntwo")
        await create_and_move_to_todo(pilot)
        pilot.app.push_screen(PinnedNoteScreen())
        await pilot.pause()

        editor = pilot.app.screen.editor
        assert editor.line_numbers
        assert gutter(editor, 1) == "1  "


async def test_the_gutter_can_be_switched_off():
    async with run_pilot() as pilot:
        pilot.app.api.vars.note_line_numbers = False
        screen = await note_of(pilot, "abc\ndef")
        editor = screen.editor

        assert editor.gutter_width == 0
        assert editor.render_line(0).text.startswith("abc")


# ------------------------------------------------------------------
# ----------------------- Chip and border --------------------------
# ------------------------------------------------------------------


async def test_pending_keys_still_show_beside_the_mode():
    async with run_pilot() as pilot:
        screen = await note_of(pilot, "abc")

        await pilot.press("d")
        await pilot.pause()

        assert screen.frame.border_subtitle == f" {MODE_NORMAL} d "


# ------------------------------------------------------------------
# ------------------------- Yank flash -----------------------------
# ------------------------------------------------------------------


def flashed(editor, y: int, x: int) -> bool:
    return cell(editor, y, x).bgcolor == theme_of(editor)[YANKED].bgcolor


async def test_a_yank_lights_up_exactly_what_it_took():
    async with run_pilot() as pilot:
        screen = await note_of(pilot, "ab cd")
        editor = screen.editor

        await pilot.press("y", "w")
        await pilot.pause()

        # The cursor's own cell, at the start, still shows the cursor
        assert editor.cursor_location == (0, 0)
        assert [flashed(editor, 0, x) for x in range(1, 5)] == [True] * 2 + [False] * 2
        assert cell(editor, 0, 1).color == theme_of(editor)[YANKED].color


async def test_a_line_yank_lights_up_the_whole_lines():
    async with run_pilot() as pilot:
        screen = await note_of(pilot, "aa\nbb\ncc", at=(1, 0))
        editor = screen.editor

        await pilot.press("2", "y", "y")
        await pilot.pause()

        assert not flashed(editor, 0, 1)
        assert editor.cursor_location == (1, 0)
        assert all(flashed(editor, y, x) for y, x in ((1, 1), (2, 0), (2, 1)))


async def test_a_visual_yank_lights_up_the_selection_back_in_normal():
    async with run_pilot() as pilot:
        screen = await note_of(pilot, "abcdef")
        editor = screen.editor

        await pilot.press("ö", "v", "ö", "ö", "y")
        await pilot.pause()

        assert editor.mode == MODE_NORMAL
        assert editor.cursor_location == (0, 1)
        assert [flashed(editor, 0, x) for x in (0, 2, 3, 4)] == [
            False,
            True,
            True,
            False,
        ]


@pytest.mark.parametrize("keys", [("d", "w"), ("c", "w"), ("x",)])
async def test_only_a_yank_flashes(keys):
    async with run_pilot() as pilot:
        screen = await note_of(pilot, "ab cd")
        editor = screen.editor

        await pilot.press(*keys)
        await pilot.pause()

        assert pilot.app.api.vim.register.register is not None
        assert not any(flashed(editor, 0, x) for x in range(3))


async def test_the_flash_goes_out_on_its_timer(monkeypatch):
    async with run_pilot() as pilot:
        screen = await note_of(pilot, "ab cd")
        editor = screen.editor

        timers: List[Tuple[float, Callable]] = []
        monkeypatch.setattr(modes, "YANK_FLASH", 0.15)
        monkeypatch.setattr(
            editor, "set_timer", lambda delay, callback: timers.append((delay, callback))
        )

        await pilot.press("y", "w")
        await pilot.pause()
        assert flashed(editor, 0, 1)

        [(delay, callback)] = timers
        assert delay == 0.15

        callback()
        await pilot.pause()
        assert not flashed(editor, 0, 1)


async def test_the_next_key_puts_the_flash_out_and_a_new_yank_starts_its_own():
    async with run_pilot() as pilot:
        screen = await note_of(pilot, "ab cd ef")
        editor = screen.editor

        await pilot.press("y", "w")
        await pilot.pause()
        assert flashed(editor, 0, 1)

        await pilot.press("w")
        await pilot.pause()
        assert not flashed(editor, 0, 1)

        await pilot.press("y", "w")
        await pilot.pause()
        assert not flashed(editor, 0, 1)
        assert flashed(editor, 0, 4)


# ------------------------------------------------------------------
# ------------------------- Help pane ------------------------------
# ------------------------------------------------------------------


HELP_KEYS = ("space", "question_mark")


async def test_space_question_mark_opens_the_help_and_closes_it_again():
    async with run_pilot() as pilot:
        screen = await note_of(pilot, "abc\ndef", at=(1, 2))

        # The space waits on the chip for its `?`
        await pilot.press("space")
        await pilot.pause()
        assert screen.frame.border_subtitle == f" {MODE_NORMAL} ␣ "

        await pilot.press("question_mark")
        await pilot.pause()

        help_screen = pilot.app.screen
        assert isinstance(help_screen, NoteHelpScreen)
        assert isinstance(help_screen, HelpScreen)
        assert help_screen.panel.border_title == "Note Keys"

        # A space alone doesn't close it, nor scroll it
        await pilot.press("space")
        await pilot.pause()
        assert pilot.app.screen is help_screen

        await pilot.press("question_mark")
        await pilot.pause()

        assert pilot.app.screen is screen
        assert screen.editor.mode == MODE_NORMAL
        assert screen.editor.cursor_location == (1, 2)


async def test_escape_closes_the_help_back_into_the_same_mode():
    async with run_pilot() as pilot:
        screen = await note_of(pilot, "abc def")
        await pilot.press("v", "w")
        await pilot.pause()

        await pilot.press(*HELP_KEYS)
        await pilot.pause()
        assert isinstance(pilot.app.screen, NoteHelpScreen)

        await pilot.press("escape")
        await pilot.pause()

        assert pilot.app.screen is screen
        assert screen.editor.mode == MODE_VISUAL
        assert screen.editor.engine.selection == ((0, 0), (0, 4))
        assert screen.editor.text == "abc def"


async def test_space_in_insert_still_types_a_space():
    async with run_pilot() as pilot:
        screen = await open_note(pilot)

        await pilot.press("a", *HELP_KEYS)
        await pilot.pause()

        assert pilot.app.screen is screen
        assert screen.editor.mode == MODE_INSERT
        assert screen.editor.text == "a ?"


async def test_question_mark_alone_is_still_the_notes_search():
    async with run_pilot() as pilot:
        screen = await note_of(pilot, "abc")

        await pilot.press("?")
        await pilot.pause()

        assert pilot.app.screen is screen
        assert screen.editor.search_prompt == ""


async def test_the_help_scrolls_with_the_notes_own_keys():
    async with run_pilot() as pilot:
        await note_of(pilot, "abc")
        await pilot.press(*HELP_KEYS)
        await pilot.pause()

        panel = pilot.app.screen.panel
        assert panel.max_scroll_y > 0

        for key, at_top in (("l", False), ("k", True), ("down", False), ("up", True)):
            await pilot.press(key)
            await pilot.pause()
            assert (panel.scroll_target_y == 0) == at_top, key

        await pilot.press("G")
        await pilot.pause()
        assert panel.scroll_target_y == panel.max_scroll_y

        await pilot.press("g", "g")
        await pilot.pause()
        assert panel.scroll_target_y == 0


def listing(table: NoteKeyTable) -> List[Tuple[str, str, str]]:
    return [(group, *row) for group in table._groups() for row in table._rows(group)]


async def test_the_help_lists_the_sections_in_order_from_the_live_keymap():
    async with run_pilot() as pilot:
        await note_of(pilot, "abc")
        await pilot.press(*HELP_KEYS)
        await pilot.pause()

        table = pilot.app.screen.query_one(NoteKeyTable)

        assert table._groups() == [
            "NORMAL",
            "INSERT",
            "VISUAL / V-LINE",
            "FLASH",
            "Note window",
        ]

        rows = listing(table)
        assert ("NORMAL", "j/ö/k/l", "left, right, up, down") in rows
        assert ("NORMAL", "u/ctrl+r", "undo / redo") in rows
        assert ("INSERT", "tab/shift+tab", "nest / unnest the line") in rows
        assert ("VISUAL / V-LINE", "y/d/c", "yank, delete, change the selection") in rows
        assert ("Note window", "gf", "go to the attached files") in rows
        assert ("Note window", "space ?", "this help") in rows


async def test_the_help_follows_a_rebind_and_leaves_out_what_has_no_key():
    async with run_pilot() as pilot:
        await note_of(pilot, "abc")
        keys = pilot.app.api.vim.keys
        keys.remap({"j": "ß", "ö": "+"})
        keys.set("zz", VimMotion.TOP)

        await pilot.press(*HELP_KEYS)
        await pilot.pause()

        rows = listing(pilot.app.screen.query_one(NoteKeyTable))
        descriptions = [description for _, _, description in rows]

        assert ("NORMAL", "ß/+/k/l", "left, right, up, down") in rows
        assert "centre the cursor line" not in descriptions


@pytest.mark.parametrize(
    "layout, moves", [("qwerty_vim.py", "h/l/k/j"), ("qwertz_vim.py", "h/l/k/j")]
)
async def test_the_help_follows_the_layout_templates(layout, moves):
    async with run_pilot() as pilot:
        await note_of(pilot, "abc")
        keys = pilot.app.api.vim.keys

        # A fresh keymap, as if the template were all there is: it binds it itself
        keys.set(" ?", VimCommand.CENTER_VIEW)
        apply_layout(pilot.app.api, layout)
        assert keys.action_for(" ?") is VimCommand.HELP

        await pilot.press(*HELP_KEYS)
        await pilot.pause()

        rows = listing(pilot.app.screen.query_one(NoteKeyTable))
        assert ("NORMAL", moves, "left, right, up, down") in rows


async def test_each_heading_wears_its_modes_color():
    async with run_pilot() as pilot:
        await note_of(pilot, "abc")
        await pilot.press(*HELP_KEYS)
        await pilot.pause()

        table = pilot.app.screen.query_one(NoteKeyTable)
        theme = pilot.app.api.vars.theme

        for group, color in (
            ("NORMAL", theme.blue),
            ("INSERT", theme.green),
            ("VISUAL / V-LINE", theme.magenta),
            ("FLASH", theme.orange),
            ("Note window", theme.primary),
        ):
            style = table._title_style(group)
            assert style.bgcolor.name.lower() == color.lower(), group
            assert style.bold


# ------------------------------------------------------------------
# ------------------------- Hint line ------------------------------
# ------------------------------------------------------------------


def hint_text(screen: NoteScreenBase) -> str:
    return str(screen.hint.render())


async def test_the_hints_are_off_by_default_and_the_line_keeps_its_row():
    async with run_pilot() as pilot:
        screen = await note_of(pilot, "abc")

        assert not pilot.app.api.vars.note_hints
        assert hint_text(screen) == ""
        height = screen.frame.size.height
        assert screen.hint.size.height == 1

        # The search prompt still shows there, and the window doesn't move
        await pilot.press("?")
        await pilot.pause()
        assert hint_text(screen).startswith("?")
        assert screen.frame.size.height == height

        await pilot.press("escape")
        await pilot.pause()
        assert hint_text(screen) == ""


async def test_the_confirm_and_messages_show_with_the_hints_off():
    async with run_pilot() as pilot:
        screen = await note_of(pilot, "abc")

        screen.report("Hello")
        assert hint_text(screen) == "Hello"

        # Clearing is INSERT's: in NORMAL the key is half a page
        await pilot.press("i", "ctrl+d")
        await pilot.pause()
        assert "Clear the whole note?" in hint_text(screen)
        assert screen.hint.has_class("confirming")


async def test_the_hints_can_be_switched_on():
    async with run_pilot() as pilot:
        pilot.app.api.vars.note_hints = True
        screen = await note_of(pilot, "abc")

        assert "i insert" in hint_text(screen)
