"""
The vim engine at work in the note window: the adapter, the keymap and the modes
"""

from unittest.mock import patch

import pytest
from rich.style import Style
from textual import events
from textual.content import Content
from textual.geometry import Offset
from textual.widgets.text_area import Selection

from tests.test_ui.test_note_ui import open_note
from tests.test_ui.ui_base import (
    boot,
    commit_line,
    create_and_move_to_todo,
    run_pilot,
    set_clipboard,
)
from todooit.api import PinnedNote, Todo
from todooit.ui.screens.note import NoteScreen, NoteScreenBase, PinnedNoteScreen
from todooit.ui.screens.note.disp.document import FoldedDocument
from todooit.ui.screens.note.disp.markup import BACKDROP, SEARCH_MATCH, TARGET
from todooit.ui.screens.note.vim.modes import MODE_INSERT, MODE_NORMAL
from todooit.vim_engine import VimCommand, VimMotion


async def note_holding(pilot, text: str) -> NoteScreen:
    """A note with `text` in it, in NORMAL, cursor on the very first character."""

    screen = await open_note(pilot)
    await pilot.press(*["enter" if char == "\n" else char for char in text])
    await pilot.press("escape")
    screen.editor.move_cursor((0, 0))
    await pilot.pause()
    return screen


async def test_an_empty_note_opens_in_normal():
    async with run_pilot() as pilot:
        await create_and_move_to_todo(pilot)
        await pilot.press("n")
        await commit_line(pilot, "task")
        await pilot.press(" ")
        await pilot.pause()

        screen = pilot.app.screen
        assert isinstance(screen, NoteScreen)
        assert screen.editor.mode == MODE_NORMAL
        assert screen.editor.read_only

        # Letters are commands here, so nothing gets written
        await pilot.press("z", "q")
        assert screen.editor.text == ""

        await pilot.press("i", "a")
        assert screen.editor.mode == MODE_INSERT
        assert screen.editor.text == "a"


async def test_a_written_note_opens_in_normal():
    async with run_pilot() as pilot:
        await note_holding(pilot, "written")
        await pilot.press("escape")
        await pilot.pause()

        await pilot.press(" ")
        await pilot.pause()

        screen = pilot.app.screen
        assert isinstance(screen, NoteScreen)
        assert screen.editor.mode == MODE_NORMAL


async def test_the_pinned_note_opens_in_normal_and_moves_the_same():
    async with run_pilot() as pilot:
        app = await boot(pilot)
        PinnedNote.set_text("abc")

        app.push_screen(PinnedNoteScreen())
        await pilot.pause()

        screen = app.screen
        assert isinstance(screen, PinnedNoteScreen)
        editor = screen.editor
        assert editor.mode == MODE_NORMAL

        await pilot.press("ö")
        assert editor.cursor_location == (0, 1)


async def test_the_default_config_puts_the_motions_on_j_ö_k_l():
    async with run_pilot() as pilot:
        app = await boot(pilot)
        keys = app.api.vim.keys

        assert keys.key_for(VimMotion.LEFT) == "j"
        assert keys.key_for(VimMotion.RIGHT) == "ö"
        assert keys.key_for(VimMotion.UP) == "k"
        assert keys.key_for(VimMotion.DOWN) == "l"


async def test_j_ö_k_l_move_the_cursor():
    async with run_pilot() as pilot:
        screen = await note_holding(pilot, "abc\ndef")
        editor = screen.editor

        await pilot.press("ö")
        assert editor.cursor_location == (0, 1)
        await pilot.press("l")
        assert editor.cursor_location == (1, 1)
        await pilot.press("j")
        assert editor.cursor_location == (1, 0)
        await pilot.press("k")
        assert editor.cursor_location == (0, 0)

        assert editor.text == "abc\ndef"


async def test_left_and_right_stay_on_their_line():
    async with run_pilot() as pilot:
        screen = await note_holding(pilot, "abc\ndef")
        editor = screen.editor

        editor.move_cursor((1, 0))
        await pilot.press("j")
        assert editor.cursor_location == (1, 0)

        editor.move_cursor((0, 2))
        await pilot.press("ö")
        assert editor.cursor_location == (0, 2)


async def test_up_and_down_stay_put_at_the_ends_of_the_note():
    async with run_pilot() as pilot:
        screen = await note_holding(pilot, "abc\ndef")
        editor = screen.editor

        editor.move_cursor((0, 1))
        await pilot.press("k")
        assert editor.cursor_location == (0, 1)

        editor.move_cursor((1, 1))
        await pilot.press("l")
        assert editor.cursor_location == (1, 1)


async def test_up_and_down_remember_the_column_across_a_short_line():
    async with run_pilot() as pilot:
        screen = await note_holding(pilot, "abcdef\nxy\nabcdef")
        editor = screen.editor

        editor.move_cursor((0, 4))
        await pilot.press("l")
        assert editor.cursor_location == (1, 1)
        await pilot.press("l")
        assert editor.cursor_location == (2, 4)


async def test_up_and_down_step_through_a_wrapped_line_by_row():
    async with run_pilot() as pilot:
        long = "word " * 80
        screen = await note_holding(pilot, f"{long.strip()}\nnext")
        editor = screen.editor

        await pilot.press("l")

        assert editor.cursor_location[0] == 0
        assert editor.cursor_location[1] > 0


async def test_remapping_a_key_in_config_changes_what_the_note_does():
    async with run_pilot() as pilot:
        screen = await note_holding(pilot, "abc")
        editor = screen.editor

        pilot.app.api.vim.keys.remap({"ö": "q"})

        await pilot.press("q")
        assert editor.cursor_location == (0, 1)

        await pilot.press("ö")
        assert editor.cursor_location == (0, 1)


async def test_the_note_does_not_follow_the_panes_direction_keys():
    async with run_pilot() as pilot:
        screen = await note_holding(pilot, "abc\ndef")
        editor = screen.editor

        pilot.app.api.keys.remap({"ö": "ß", "l": "§"})
        assert pilot.app.api.motion_keys().right == "ß"

        await pilot.press("ß")
        assert editor.cursor_location == (0, 0)

        await pilot.press("ö", "l")
        assert editor.cursor_location == (1, 1)

        assert "jö/kl move" in str(screen.hint.render())


async def test_the_hint_shows_the_notes_own_keys():
    async with run_pilot() as pilot:
        screen = await note_holding(pilot, "abc")

        pilot.app.api.vim.keys.remap({"j": "+"})
        screen.mode_changed()

        assert "+ö/kl move" in str(screen.hint.render())


async def test_the_strip_still_follows_the_panes_keys(tmp_path):
    # The calendar and help are held to the same in test_keyboard_layouts
    async with run_pilot() as pilot:
        files = [tmp_path / "a.txt", tmp_path / "b.txt"]
        for path in files:
            path.write_text("x")

        screen = await open_note(pilot)
        await pilot.press("escape")
        screen.attach(files)
        pilot.app.api.keys.remap({"j": "a", "ö": "w"})

        screen.pick_files()
        await pilot.pause()
        assert screen.files.picked == 1

        await pilot.press("a")
        assert screen.files.picked == 0
        await pilot.press("w")
        assert screen.files.picked == 1


async def test_the_cursor_is_clamped_to_the_last_character_after_insert():
    async with run_pilot() as pilot:
        screen = await open_note(pilot)
        await pilot.press(*"abc")
        assert screen.editor.cursor_location == (0, 3)

        await pilot.press("escape")

        assert screen.editor.cursor_location == (0, 2)


async def test_insert_can_stand_past_the_last_character():
    async with run_pilot() as pilot:
        screen = await open_note(pilot)
        await pilot.press(*"abc", "end")

        assert screen.editor.cursor_location == (0, 3)


async def test_no_way_of_placing_the_cursor_gets_past_the_last_character():
    async with run_pilot() as pilot:
        screen = await note_holding(pilot, "abc\nde")
        editor = screen.editor

        editor.move_cursor((0, 3))
        assert editor.cursor_location == (0, 2)

        await pilot.press("end")
        assert editor.cursor_location == (0, 2)

        await pilot.press("G")
        assert editor.cursor_location == (1, 1)

        await pilot.press("_")
        assert editor.cursor_location == (1, 1)


async def test_a_click_past_the_end_of_a_line_lands_on_its_last_character():
    async with run_pilot() as pilot:
        screen = await note_holding(pilot, "abc\nde")

        await pilot.click(screen.editor, offset=Offset(40, 0))

        assert screen.editor.cursor_location == (0, 2)


async def test_a_selection_may_still_reach_the_end_of_the_line():
    async with run_pilot() as pilot:
        screen = await note_holding(pilot, "abc")
        editor = screen.editor

        await pilot.press("shift+end")

        assert editor.selection == Selection((0, 0), (0, 3))


async def test_escape_goes_to_normal_from_insert_then_closes_from_normal():
    async with run_pilot() as pilot:
        screen = await open_note(pilot)
        assert screen.editor.mode == MODE_INSERT
        await pilot.press(*"kept")

        await pilot.press("escape")
        await pilot.pause()
        assert pilot.app.screen is screen
        assert screen.editor.mode == MODE_NORMAL

        await pilot.press("escape")
        await pilot.pause()
        assert not isinstance(pilot.app.screen, NoteScreenBase)
        assert Todo.all()[0].note == "kept"


async def test_a_key_between_two_gs_cancels_the_gg_without_moving():
    async with run_pilot() as pilot:
        screen = await note_holding(pilot, "abc\ndef")
        editor = screen.editor
        editor.move_cursor((1, 1))

        await pilot.press("g", "j", "g")

        assert editor.cursor_location == (1, 1)
        assert editor.engine.pending == "g"


async def test_word_motions_and_counts_move_the_cursor():
    async with run_pilot() as pilot:
        screen = await note_holding(pilot, "one größe three four")
        editor = screen.editor

        await pilot.press("w")
        assert editor.cursor_location == (0, 4)
        await pilot.press("e")
        assert editor.cursor_location == (0, 8)
        await pilot.press("b")
        assert editor.cursor_location == (0, 4)
        await pilot.press("2", "w")
        assert editor.cursor_location == (0, 16)


async def test_the_default_config_has_the_line_and_character_motions():
    async with run_pilot() as pilot:
        screen = await note_holding(pilot, "  one two\n  three")
        editor = screen.editor

        await pilot.press("_")
        assert editor.cursor_location == (0, 8)
        await pilot.press("=")
        assert editor.cursor_location == (0, 2)
        await pilot.press("ä")
        assert editor.cursor_location == (1, 2)
        await pilot.press("ü")
        assert editor.cursor_location == (0, 2)

        await pilot.press("f", "space")
        assert editor.cursor_location == (0, 5)
        await pilot.press("F", "e")
        assert editor.cursor_location == (0, 4)
        await pilot.press("t", "w")
        assert editor.cursor_location == (0, 6)
        await pilot.press("T", "n")
        assert editor.cursor_location == (0, 4)

        await pilot.press("f", "o")
        assert editor.cursor_location == (0, 8)
        await pilot.press("H")
        assert editor.cursor_location == (0, 2)
        await pilot.press("h")
        assert editor.cursor_location == (0, 8)


async def test_a_partial_command_shows_beside_the_mode_chip():
    async with run_pilot() as pilot:
        screen = await note_holding(pilot, "abc abc")
        frame = screen.frame
        assert frame.border_subtitle == " NORMAL "

        await pilot.press("2")
        assert frame.border_subtitle == " NORMAL 2 "

        await pilot.press("f")
        assert frame.border_subtitle == " NORMAL 2f "

        await pilot.press("c")
        assert frame.border_subtitle == " NORMAL "
        assert screen.editor.cursor_location == (0, 6)


async def test_an_invalid_key_clears_the_partial_command_from_the_chip():
    async with run_pilot() as pilot:
        screen = await note_holding(pilot, "abc")

        await pilot.press("2", "Q")

        assert screen.frame.border_subtitle == " NORMAL "
        assert screen.editor.cursor_location == (0, 0)


async def test_a_message_in_the_hint_line_survives_a_partial_command():
    async with run_pilot() as pilot:
        screen = await note_holding(pilot, "abc")
        screen.report("a message")

        await pilot.press("2")

        assert "a message" in str(screen.hint.render())


async def test_a_partial_command_that_holds_markup_is_shown_as_typed():
    async with run_pilot() as pilot:
        app = await boot(pilot)
        app.api.vim.keys.set("[b]x", VimMotion.RIGHT)
        PinnedNote.set_text("abc")
        app.push_screen(PinnedNoteScreen())
        await pilot.pause()
        screen = app.screen
        assert isinstance(screen, PinnedNoteScreen)

        await pilot.press("[", "b", "]")
        await pilot.pause()

        subtitle = screen.frame.border_subtitle
        assert subtitle is not None
        assert Content.from_markup(subtitle).plain == " NORMAL [b] "


async def test_escape_cancels_a_partial_command_and_leaves_the_note_open():
    async with run_pilot() as pilot:
        screen = await note_holding(pilot, "abc")

        for keys in (["2"], ["f"], ["3", "t"]):
            await pilot.press(*keys)
            await pilot.press("escape")
            await pilot.pause()

            assert pilot.app.screen is screen
            assert screen.frame.border_subtitle == " NORMAL "
            assert screen.editor.engine.pending == ""

        await pilot.press("escape")
        await pilot.pause()
        assert not isinstance(pilot.app.screen, NoteScreenBase)


async def test_escape_after_a_g_cancels_it_and_leaves_the_note_open():
    async with run_pilot() as pilot:
        screen = await note_holding(pilot, "abc")

        await pilot.press("g", "escape")
        await pilot.pause()
        assert pilot.app.screen is screen

        await pilot.press("escape")
        await pilot.pause()
        assert not isinstance(pilot.app.screen, NoteScreenBase)


async def test_gf_opens_the_strip_now_that_f_jumps_to_a_character(tmp_path):
    async with run_pilot() as pilot:
        screen = await note_holding(pilot, "abc")
        paper = tmp_path / "paper.pdf"
        paper.write_text("x")
        screen.attach([str(paper)])

        await pilot.press("f", "c")
        assert screen.editor.cursor_location == (0, 2)
        assert not screen.picking_files

        await pilot.press("g", "f")
        assert screen.picking_files


def cell(editor, y: int, x: int) -> Style:
    """The style of one cell of the note as it's drawn."""

    at = 0
    for segment in editor.render_line(y):
        if at <= x < at + segment.cell_length:
            return segment.style
        at += segment.cell_length

    raise AssertionError(f"nothing is drawn at {x},{y}")


def theme_of(editor) -> dict:
    return editor._theme.syntax_styles


async def test_f_dims_the_text_ahead_while_it_waits_for_its_character():
    async with run_pilot() as pilot:
        screen = await note_holding(pilot, "abc abc\nbelow")
        editor = screen.editor
        dim = theme_of(editor)[BACKDROP].color

        editor.move_cursor((0, 2))
        await pilot.pause()
        assert cell(editor, 0, 4).color != dim

        await pilot.press("f")
        await pilot.pause()

        assert cell(editor, 0, 1).color != dim
        assert cell(editor, 0, 4).color == dim
        assert cell(editor, 1, 0).color == dim


async def test_capital_f_dims_the_text_behind_instead():
    async with run_pilot() as pilot:
        screen = await note_holding(pilot, "above\nabc abc\nbelow")
        editor = screen.editor
        dim = theme_of(editor)[BACKDROP].color

        editor.move_cursor((1, 4))
        await pilot.pause()

        await pilot.press("F")
        await pilot.pause()

        assert cell(editor, 0, 0).color == dim
        assert cell(editor, 1, 1).color == dim
        assert cell(editor, 1, 6).color != dim
        assert cell(editor, 2, 0).color != dim


async def test_a_jump_lights_up_where_it_can_go_next():
    async with run_pilot() as pilot:
        screen = await note_holding(pilot, "abcabcabc")
        editor = screen.editor
        target = theme_of(editor)[TARGET].bgcolor

        await pilot.press("f", "c")
        await pilot.pause()
        assert editor.cursor_location == (0, 2)
        assert cell(editor, 0, 5).bgcolor == target
        assert cell(editor, 0, 8).bgcolor == target
        assert cell(editor, 0, 4).bgcolor != target

        # All stay marked, passed or not, and the text passed stays dim
        await pilot.press("h")
        await pilot.pause()
        assert editor.cursor_location == (0, 5)
        assert cell(editor, 0, 2).bgcolor == target
        assert cell(editor, 0, 8).bgcolor == target
        assert cell(editor, 0, 3).color == theme_of(editor)[BACKDROP].color

        await pilot.press("H")
        await pilot.pause()
        assert editor.cursor_location == (0, 2)
        assert cell(editor, 0, 5).bgcolor == target


async def test_t_lights_up_the_cell_it_would_land_on():
    async with run_pilot() as pilot:
        screen = await note_holding(pilot, "abcabcabc")
        editor = screen.editor
        target = theme_of(editor)[TARGET].bgcolor

        await pilot.press("t", "c")
        await pilot.pause()

        assert editor.cursor_location == (0, 1)
        assert cell(editor, 0, 4).bgcolor == target
        assert cell(editor, 0, 5).bgcolor != target


async def test_the_targets_land_right_after_a_multibyte_character():
    async with run_pilot() as pilot:
        screen = await note_holding(pilot, "üü x üü x")
        editor = screen.editor
        target = theme_of(editor)[TARGET].bgcolor

        await pilot.press("f", "x")
        await pilot.pause()

        assert editor.cursor_location == (0, 3)
        assert cell(editor, 0, 8).bgcolor == target


async def test_a_target_on_a_rendered_line_is_marked_and_landed_on():
    async with run_pilot() as pilot:
        screen = await note_holding(pilot, "a c\n**b** c")
        editor = screen.editor
        target = theme_of(editor)[TARGET].bgcolor

        await pilot.press("f", "c")
        await pilot.pause()

        # Drawn as `b c`, with the marks off the page
        assert editor.cursor_location == (0, 2)
        assert cell(editor, 1, 2).bgcolor == target

        await pilot.press("h")
        await pilot.pause()
        assert editor.cursor_location == (1, 6)


async def test_the_cursor_still_shows_on_a_dimmed_row():
    async with run_pilot() as pilot:
        screen = await note_holding(pilot, "a\nc c")
        editor = screen.editor
        theme = editor._theme
        assert theme.cursor_style is not None

        await pilot.press("f", "c")
        await pilot.pause()

        assert editor.cursor_location == (1, 0)
        assert cell(editor, 1, 0).bgcolor == theme.cursor_style.bgcolor
        assert cell(editor, 1, 2).bgcolor == theme_of(editor)[TARGET].bgcolor
        assert cell(editor, 1, 1).color == theme_of(editor)[BACKDROP].color


async def test_a_jump_only_goes_as_far_as_the_note_on_screen():
    async with run_pilot() as pilot:
        lines = ["x"] * 200
        lines[199] = "c"
        screen = await note_holding(pilot, "\n".join(lines[:3]))
        editor = screen.editor
        editor.load_text("\n".join(lines))
        await pilot.pause()
        editor.move_cursor((0, 0))
        await pilot.pause()

        await pilot.press("f", "c")
        await pilot.pause()

        assert editor.cursor_location == (0, 0)


async def test_markup_drawn_on_its_own_dims_with_the_rest():
    async with run_pilot() as pilot:
        screen = await note_holding(pilot, "abc\n---\n# head\n- item\n> quote")
        editor = screen.editor
        dim = theme_of(editor)[BACKDROP].color
        base_style = editor._theme.base_style
        assert base_style is not None
        base = base_style.bgcolor

        await pilot.press("f")
        await pilot.pause()

        for y in range(1, 5):
            assert cell(editor, y, 0).color == dim, y
            assert cell(editor, y, 0).bgcolor == base, y


async def test_escape_clears_the_showing_then_closes_the_note():
    async with run_pilot() as pilot:
        screen = await note_holding(pilot, "abcabc\nbelow")
        editor = screen.editor
        dim = theme_of(editor)[BACKDROP].color

        await pilot.press("f", "c")
        await pilot.pause()
        assert cell(editor, 1, 0).color == dim

        await pilot.press("escape")
        await pilot.pause()
        assert pilot.app.screen is screen
        assert cell(editor, 1, 0).color != dim

        await pilot.press("escape")
        await pilot.pause()
        assert not isinstance(pilot.app.screen, NoteScreenBase)


async def test_another_key_clears_the_showing_and_still_does_its_job():
    async with run_pilot() as pilot:
        screen = await note_holding(pilot, "abcabc\nbelow")
        editor = screen.editor
        dim = theme_of(editor)[BACKDROP].color

        await pilot.press("f", "c", "j")
        await pilot.pause()

        assert editor.cursor_location == (0, 1)
        assert cell(editor, 1, 0).color != dim


async def test_a_key_the_engine_leaves_to_the_note_clears_the_showing_too():
    async with run_pilot() as pilot:
        screen = await note_holding(pilot, "abcabc\nbelow")
        editor = screen.editor
        dim = theme_of(editor)[BACKDROP].color

        await pilot.press("f", "c", "G")
        await pilot.pause()

        assert cell(editor, 1, 0).color != dim


async def test_going_into_insert_clears_the_showing():
    async with run_pilot() as pilot:
        screen = await note_holding(pilot, "abcabc\nbelow")
        editor = screen.editor
        dim = theme_of(editor)[BACKDROP].color

        await pilot.press("f", "c", "i")
        await pilot.pause()

        assert editor.mode == MODE_INSERT
        assert cell(editor, 1, 0).color != dim


async def test_moving_the_cursor_without_a_key_clears_the_showing():
    async with run_pilot() as pilot:
        screen = await note_holding(pilot, "abcabc\nbelow")
        editor = screen.editor
        dim = theme_of(editor)[BACKDROP].color

        await pilot.press("f", "c")
        await pilot.pause()

        # As a click does
        editor.move_cursor((0, 0))
        await pilot.pause()

        assert cell(editor, 1, 0).color != dim


# How much of the text is kept in view above and below the cursor
CONTEXT = 4


async def long_note(pilot, lines: int = 200, line: str = "line {n}") -> NoteScreen:
    """A note too long for the window, in NORMAL, cursor on the very first character."""

    screen = await open_note(pilot)
    screen.editor.load_text("\n".join(line.format(n=n) for n in range(lines)))
    await pilot.press("escape")
    await pilot.pause()
    assert screen.editor.cursor_location == (0, 0)
    return screen


def rows_above_cursor(editor) -> int:
    return editor.cursor_y - editor.scroll_offset.y


def rows_below_cursor(editor) -> int:
    return editor.content_size.height - 1 - rows_above_cursor(editor)


async def test_half_page_keys_carry_the_cursor_and_the_view_together():
    async with run_pilot() as pilot:
        screen = await long_note(pilot)
        editor = screen.editor
        half = editor.content_size.height // 2
        assert half > CONTEXT

        # The view goes half a page; the cursor can't stay on the top row of it
        await pilot.press("ctrl+d")
        assert editor.scroll_offset.y == half
        assert editor.cursor_location == (half + CONTEXT, 0)

        await pilot.press("ctrl+d")
        assert editor.scroll_offset.y == half * 2
        assert editor.cursor_location == (half * 2 + CONTEXT, 0)

        await pilot.press("ctrl+u")
        assert editor.scroll_offset.y == half
        assert editor.cursor_location == (half + CONTEXT, 0)

        await pilot.press("ctrl+u")
        assert editor.scroll_offset.y == 0
        assert editor.cursor_location == (CONTEXT, 0)

        assert editor.mode == MODE_NORMAL
        assert not screen.awaiting_answer


async def test_cmd_stands_for_ctrl_on_the_half_page_keys():
    async with run_pilot() as pilot:
        screen = await long_note(pilot)
        editor = screen.editor
        half = editor.content_size.height // 2

        await pilot.press("super+d")
        assert editor.scroll_offset.y == half

        await pilot.press("super+u")
        assert editor.scroll_offset.y == 0
        assert not screen.awaiting_answer


async def test_half_page_keys_keep_the_column():
    async with run_pilot() as pilot:
        screen = await long_note(pilot)
        editor = screen.editor

        await pilot.press("ö", "ö", "ctrl+d")
        assert editor.cursor_location[1] == 2


async def test_half_page_keys_stop_at_the_ends_of_the_note():
    async with run_pilot() as pilot:
        screen = await long_note(pilot, lines=60)
        editor = screen.editor

        await pilot.press(*["ctrl+d"] * 10)
        assert editor.cursor_location[0] == 59
        assert editor.scroll_offset.y == editor.max_scroll_y

        await pilot.press(*["ctrl+u"] * 10)
        assert editor.cursor_location[0] == 0
        assert editor.scroll_offset.y == 0


async def test_in_insert_ctrl_d_still_clears_and_ctrl_u_does_nothing():
    async with run_pilot() as pilot:
        screen = await long_note(pilot, lines=3)
        editor = screen.editor

        await pilot.press("i", "ctrl+d")
        assert screen.awaiting_answer

        await pilot.press("n", "ctrl+u")
        assert editor.text == "line 0\nline 1\nline 2"


async def test_gg_and_g_bring_the_ends_of_the_note_into_view():
    async with run_pilot() as pilot:
        screen = await long_note(pilot)
        editor = screen.editor

        await pilot.press("ö", "G")
        assert editor.cursor_location == (199, 1)
        assert editor.scroll_offset.y == editor.max_scroll_y

        await pilot.press("g", "g")
        assert editor.cursor_location == (0, 1)
        assert editor.scroll_offset.y == 0


async def test_a_count_on_g_goes_to_that_line_with_context_around_it():
    async with run_pilot() as pilot:
        screen = await long_note(pilot)
        editor = screen.editor

        await pilot.press("1", "0", "0", "G")
        assert editor.cursor_location[0] == 99
        assert rows_below_cursor(editor) == CONTEXT


async def test_braces_move_by_paragraph_and_bring_it_into_view():
    async with run_pilot() as pilot:
        screen = await open_note(pilot)
        editor = screen.editor
        filler = "\n".join("text" for _ in range(60))
        editor.load_text(f"{filler}\n\n{filler}")
        await pilot.press("escape")
        await pilot.pause()

        await pilot.press("}")
        assert editor.cursor_location == (60, 0)
        assert rows_below_cursor(editor) == CONTEXT

        await pilot.press("}")
        assert editor.cursor_location == (120, 3)

        await pilot.press("{")
        assert editor.cursor_location == (60, 0)
        assert rows_above_cursor(editor) == CONTEXT

        await pilot.press("{")
        assert editor.cursor_location == (0, 0)


async def test_zz_puts_the_cursor_in_the_middle_of_the_view():
    async with run_pilot() as pilot:
        screen = await long_note(pilot)
        editor = screen.editor

        await pilot.press("1", "0", "0", "G")
        await pilot.press("z", "z")

        assert editor.cursor_location[0] == 99
        assert rows_above_cursor(editor) == (editor.content_size.height - 1) // 2


async def test_zz_near_the_top_of_the_note_does_what_it_can():
    async with run_pilot() as pilot:
        screen = await long_note(pilot)
        editor = screen.editor

        await pilot.press("l", "z", "z")

        assert editor.cursor_location == (1, 0)
        assert editor.scroll_offset.y == 0


async def test_context_is_kept_below_the_cursor_going_down():
    async with run_pilot() as pilot:
        screen = await long_note(pilot, lines=60)
        editor = screen.editor
        last_y = editor.virtual_size.height - 1

        for _ in range(59):
            await pilot.press("l")
            y = editor.cursor_location[0]
            assert rows_below_cursor(editor) >= min(CONTEXT, last_y - y)
            assert rows_above_cursor(editor) >= min(CONTEXT, y)

        assert rows_below_cursor(editor) == 0


async def test_context_is_kept_above_the_cursor_going_up():
    async with run_pilot() as pilot:
        screen = await long_note(pilot, lines=60)
        editor = screen.editor

        await pilot.press("G")

        for _ in range(59):
            await pilot.press("k")
            y = editor.cursor_location[0]
            assert rows_above_cursor(editor) >= min(CONTEXT, y)
            assert rows_below_cursor(editor) >= min(CONTEXT, 59 - y)

        assert editor.scroll_offset.y == 0


async def test_context_counts_rows_as_drawn_across_wrapped_lines():
    async with run_pilot() as pilot:
        screen = await long_note(pilot, lines=40, line="word " * 60)
        editor = screen.editor
        assert editor.virtual_size.height > 40

        for _ in range(60):
            await pilot.press("l")
            assert rows_below_cursor(editor) >= CONTEXT or (
                editor.scroll_offset.y == editor.max_scroll_y
            )
            assert rows_above_cursor(editor) >= CONTEXT or editor.scroll_offset.y == 0

        assert editor.scroll_offset.y > 0


async def test_context_is_kept_in_insert_too():
    async with run_pilot() as pilot:
        screen = await long_note(pilot)
        editor = screen.editor

        await pilot.press("1", "0", "0", "G", "i", "down", "down")

        assert editor.cursor_location[0] == 101
        assert rows_below_cursor(editor) == CONTEXT


async def test_a_window_too_short_for_the_context_keeps_the_cursor_in_the_middle():
    async with run_pilot() as pilot:
        screen = await long_note(pilot)
        editor = screen.editor
        await pilot.resize_terminal(80, 10)
        await pilot.pause()

        height = editor.content_size.height
        assert 1 < height <= 2 * CONTEXT

        await pilot.press("1", "0", "0", "G")
        assert rows_below_cursor(editor) == (height - 1) // 2

        await pilot.press("k")
        assert rows_above_cursor(editor) == (height - 1) // 2


async def test_down_without_a_count_goes_by_screen_row_and_with_one_by_line():
    async with run_pilot() as pilot:
        screen = await long_note(pilot, lines=3, line="word " * 60)
        editor = screen.editor
        wrapped = editor.wrapped_document
        assert len(wrapped.get_offsets(0)) >= 1

        # Still on the first line, one row down
        await pilot.press("l")
        assert editor.cursor_location[0] == 0
        assert editor.cursor_location[1] > 0

        await pilot.press("k")
        assert editor.cursor_location == (0, 0)

        await pilot.press("1", "l")
        assert editor.cursor_location == (1, 0)

        await pilot.press("1", "k")
        assert editor.cursor_location == (0, 0)


async def test_a_counted_move_keeps_its_column_across_a_short_line():
    async with run_pilot() as pilot:
        screen = await note_holding(pilot, "abcdefgh\nab\nabcdefgh")
        editor = screen.editor
        await pilot.press("6", "ö")
        assert editor.cursor_location == (0, 6)

        await pilot.press("1", "l")
        assert editor.cursor_location == (1, 1)

        await pilot.press("1", "l")
        assert editor.cursor_location == (2, 6)


async def test_a_counted_move_lands_on_the_stored_column_of_a_folded_line():
    async with run_pilot() as pilot:
        screen = await note_holding(pilot, "# abcdefgh\n\n# abcdefgh")
        editor = screen.editor
        await pilot.press("5", "ö")
        assert editor.cursor_location == (0, 5)

        await pilot.press("2", "l")
        assert editor.cursor_location == (2, 5)


async def test_half_page_keys_keep_the_cursor_in_view_across_lines_that_unfold():
    link = "[a link](https://example.com/" + "x" * 400 + ")"
    lines = [link if n % 3 == 0 else f"line {n}" for n in range(200)]

    async with run_pilot() as pilot:
        screen = await open_note(pilot)
        editor = screen.editor
        editor.load_text("\n".join(lines))
        await pilot.press("escape")
        await pilot.pause()

        for key, presses in (("ctrl+d", 5), ("ctrl+u", 5)):
            for _ in range(presses):
                await pilot.press(key)
                assert rows_above_cursor(editor) >= min(CONTEXT, editor.scroll_offset.y)
                assert rows_below_cursor(editor) >= 0


async def test_gf_ends_a_character_jump_that_is_showing():
    async with run_pilot() as pilot:
        screen = await note_holding(pilot, "abcabc")
        editor = screen.editor

        await pilot.press("f", "b")
        assert editor.engine.find_view is not None

        await pilot.press("g", "f")
        assert editor.engine.find_view is None
        assert editor.overlay is None


async def test_gf_with_a_count_is_still_gf():
    async with run_pilot() as pilot:
        screen = await note_holding(pilot, "abcabc")

        await pilot.press("2", "g", "f")

        assert screen.editor.engine.pending == ""
        assert screen.editor.cursor_location == (0, 0)


def links_opened_into(opened: list):
    """Patches the browser out of the note window, listing what it's asked to open."""

    def open_url(url: str) -> bool:
        opened.append(url)
        return True

    return patch("todooit.ui.screens.note.screens.screen.open_url", open_url)


async def test_gx_opens_the_link_under_the_cursor():
    opened: list = []

    async with run_pilot() as pilot:
        with links_opened_into(opened):
            screen = await note_holding(pilot, "see https://example.com here")

            screen.editor.move_cursor((0, 6))
            await pilot.press("g", "x")
            await pilot.pause()

            assert opened == ["https://example.com"]
            assert "Opening" in str(screen.hint.render())
            assert screen.editor.mode == MODE_NORMAL


async def test_gx_says_so_when_there_is_no_link():
    opened: list = []

    async with run_pilot() as pilot:
        with links_opened_into(opened):
            screen = await note_holding(pilot, "see https://example.com here")

            await pilot.press("g", "x")
            await pilot.pause()

            assert opened == []
            assert "No link under the cursor" in str(screen.hint.render())
            assert screen.editor.mode == MODE_NORMAL


async def test_gf_with_nothing_attached_says_so():
    async with run_pilot() as pilot:
        screen = await note_holding(pilot, "abc")

        await pilot.press("g", "f")
        await pilot.pause()

        assert not screen.picking_files
        assert "Nothing attached" in str(screen.hint.render())


@pytest.mark.parametrize("key", ["0", "$"])
async def test_the_old_note_keys_do_nothing_now(key):
    opened: list = []
    text = "\n".join(f"https://example.com/{row}" for row in range(60))

    async with run_pilot() as pilot:
        with links_opened_into(opened):
            screen = await note_holding(pilot, text)
            editor = screen.editor

            editor.move_cursor((30, 5))
            await pilot.pause()
            scrolled = editor.scroll_offset

            await pilot.press(key)
            await pilot.pause()

            assert editor.text == text
            assert editor.cursor_location == (30, 5)
            assert editor.scroll_offset == scrolled
            assert editor.mode == MODE_NORMAL
            assert editor.engine.pending == ""
            assert opened == []


async def test_f_no_longer_opens_the_strip(tmp_path):
    async with run_pilot() as pilot:
        screen = await note_holding(pilot, "abc")
        paper = tmp_path / "paper.pdf"
        paper.write_text("x")
        screen.attach([str(paper)])

        await pilot.press("f")
        await pilot.pause()

        assert not screen.picking_files
        assert screen.editor.engine.pending == "f"


@pytest.mark.parametrize(
    "up, down", [("ctrl+u", "ctrl+d"), ("super+u", "super+d")]
)
async def test_half_page_keys_in_normal_scroll_and_never_edit(up, down):
    text = "\n".join(f"line {row}" for row in range(100))

    async with run_pilot() as pilot:
        screen = await note_holding(pilot, text)
        editor = screen.editor
        half = editor.half_page()

        await pilot.press(down)
        await pilot.pause()
        assert editor.scroll_offset.y == half
        assert not screen.awaiting_answer

        await pilot.press(up)
        await pilot.pause()
        assert editor.scroll_offset.y == 0
        assert editor.text == text


@pytest.mark.parametrize("key", ["ctrl+u", "super+u"])
async def test_in_insert_the_up_key_does_nothing(key):
    async with run_pilot() as pilot:
        screen = await note_holding(pilot, "above\nthis one\nbelow")
        editor = screen.editor

        editor.move_cursor((1, 3))
        await pilot.press("i", key)
        await pilot.pause()

        assert editor.text == "above\nthis one\nbelow"
        assert editor.cursor_location == (1, 3)
        assert editor.mode == MODE_INSERT


@pytest.mark.parametrize("key", ["ctrl+d", "super+d"])
async def test_in_insert_the_down_key_clears_the_note_after_asking(key):
    async with run_pilot() as pilot:
        screen = await note_holding(pilot, "precious")
        editor = screen.editor

        await pilot.press("i", key)
        await pilot.pause()
        assert screen.awaiting_answer

        await pilot.press("n")
        await pilot.pause()
        assert editor.text == "precious"

        await pilot.press(key, "y")
        await pilot.pause()
        assert editor.text == ""


async def test_a_clear_key_left_to_the_editor_never_clears_from_normal():
    async with run_pilot() as pilot:
        screen = await note_holding(pilot, "precious")

        pilot.app.api.vim.keys.remap({"<ctrl+d>": "<ctrl+f>"})

        await pilot.press("ctrl+d")
        await pilot.pause()

        assert not screen.awaiting_answer
        assert screen.editor.text == "precious"


@pytest.mark.parametrize("key, letter", [("super+u", "u"), ("super+d", "d")])
async def test_a_cmd_chord_with_its_letter_attached_types_nothing_in_insert(key, letter):
    async with run_pilot() as pilot:
        screen = await note_holding(pilot, "abc")

        await pilot.press("i")
        pilot.app.post_message(events.Key(key, letter))
        await pilot.pause()

        assert letter not in screen.editor.text


async def test_ctrl_a_and_shift_selection_work_in_normal():
    async with run_pilot() as pilot:
        screen = await note_holding(pilot, "abc\ndef")
        editor = screen.editor

        await pilot.press("shift+right", "shift+right")
        await pilot.pause()
        assert editor.selected_text == "ab"

        await pilot.press("ctrl+a")
        await pilot.pause()
        assert editor.selected_text == "abc\ndef"
        assert editor.mode == MODE_NORMAL


async def test_copy_cut_and_paste_work_from_normal():
    async with run_pilot() as pilot:
        screen = await note_holding(pilot, "abc\ndef")
        editor = screen.editor

        await pilot.press("ctrl+c")
        await pilot.pause()
        assert pilot.app.clipboard == "abc\ndef"
        assert editor.mode == MODE_NORMAL

        await pilot.press("shift+right", "ctrl+x")
        await pilot.pause()
        assert pilot.app.clipboard == "a"
        assert editor.text == "bc\ndef"
        assert editor.mode == MODE_INSERT

        await pilot.press("escape")
        set_clipboard("pasted ")
        editor.move_cursor((0, 0))
        await pilot.press("ctrl+v")
        await pilot.pause()
        assert editor.text == "pasted bc\ndef"
        assert editor.mode == MODE_INSERT


async def test_the_normal_hint_is_built_from_the_configured_keys():
    async with run_pilot() as pilot:
        screen = await note_holding(pilot, "abc")

        hint = str(screen.hint.render())
        for shown in (
            "i insert",
            "jö/kl move",
            "C-u/C-d half page",
            "gx link",
            "gf files",
            "esc close",
        ):
            assert shown in hint

        pilot.app.api.vim.keys.remap(
            {"i": "+", "<ctrl+u>": "<ctrl+b>", "<ctrl+d>": "<ctrl+f>", "gx": "gl"}
        )
        screen.mode_changed()

        hint = str(screen.hint.render())
        for shown in ("+ insert", "C-b/C-f half page", "gl link"):
            assert shown in hint


async def test_the_normal_hint_leaves_out_what_has_no_key():
    async with run_pilot() as pilot:
        screen = await note_holding(pilot, "abc")

        pilot.app.api.vim.keys.set("gx", VimCommand.CENTER_VIEW)
        screen.mode_changed()

        hint = str(screen.hint.render())
        assert "link" not in hint
        assert "gf files" in hint


async def test_a_long_note_scrolls_without_a_scrollbar():
    async with run_pilot() as pilot:
        screen = await note_holding(pilot, "\n".join(f"line {n}" for n in range(100)))
        editor = screen.editor

        assert editor.max_scroll_y > 0
        assert editor.scrollbar_size_vertical == 0
        assert editor.content_size.width == editor.size.width

        await pilot.press("ctrl+d")
        await pilot.pause()
        assert editor.scroll_offset.y > 0


# --- The delete operator ------------------------------------------------------


async def note_of(pilot, text: str, at=(0, 0)) -> NoteScreen:
    """A note holding exactly `text`, with no list carried on by the typing of it."""

    screen = await open_note(pilot)
    await pilot.press("escape")
    screen.editor.text = text
    screen.editor.move_cursor(at)
    await pilot.pause()
    return screen


async def test_bare_d_no_longer_scrolls_it_waits_for_a_motion():
    text = "\n".join(f"line {row}" for row in range(60))

    async with run_pilot() as pilot:
        screen = await note_of(pilot, text, (30, 2))
        editor = screen.editor
        scrolled = editor.scroll_offset

        await pilot.press("d")
        await pilot.pause()

        assert editor.text == text
        assert editor.cursor_location == (30, 2)
        assert editor.scroll_offset == scrolled
        assert editor.engine.pending == "d"


async def test_a_delete_goes_all_the_way_to_the_todo():
    async with run_pilot() as pilot:
        screen = await note_of(pilot, "foo bar baz")
        todo = screen.todo

        await pilot.press("d", "w")
        assert screen.editor.text == "bar baz"
        assert screen.editor.read_only

        await pilot.press("escape")
        await pilot.pause()

        assert not isinstance(pilot.app.screen, NoteScreen)
        assert todo.note == "bar baz"


@pytest.mark.parametrize(
    "keys, text",
    [
        (("2", "d", "3", "w"), "g h"),
        (("d", "e"), " c d e f g h"),
        (("x",), " b c d e f g h"),
        (("D",), ""),
        (("d", "_"), ""),
        (("d", "t", "c"), "c d e f g h"),
        (("d", "d"), ""),
    ],
)
async def test_deletes_through_the_real_keymap(keys, text):
    async with run_pilot() as pilot:
        screen = await note_of(pilot, "a b c d e f g h")

        await pilot.press(*keys)

        assert screen.editor.text == text
        assert screen.editor.mode == MODE_NORMAL


async def test_three_dd_deletes_three_lines():
    async with run_pilot() as pilot:
        screen = await note_of(pilot, "a\nb\nc\nd\ne", (1, 0))

        await pilot.press("3", "d", "d")

        assert screen.editor.text == "a\ne"
        assert screen.editor.cursor_location == (1, 0)


async def test_the_partial_command_shows_beside_the_chip_and_escape_cancels_it():
    async with run_pilot() as pilot:
        screen = await note_of(pilot, "abc def")
        frame = screen.frame

        await pilot.press("2")
        await pilot.press("d")
        assert frame.border_subtitle == " NORMAL 2d "

        await pilot.press("3")
        assert frame.border_subtitle == " NORMAL 2d3 "

        # Cancels the command, and leaves the window open
        await pilot.press("escape")
        await pilot.pause()
        assert pilot.app.screen is screen
        assert frame.border_subtitle == " NORMAL "
        assert screen.editor.text == "abc def"

        await pilot.press("escape")
        await pilot.pause()
        assert pilot.app.screen is not screen


async def test_an_invalid_key_cancels_a_delete_and_goes_no_further():
    async with run_pilot() as pilot:
        screen = await note_of(pilot, "abc def")

        await pilot.press("d", "q")

        assert screen.frame.border_subtitle == " NORMAL "
        assert screen.editor.text == "abc def"


LINK = "[x](http://c.d)"


@pytest.mark.parametrize(
    "text, at, keys, after",
    [
        # Into a rendered row, where a stored column is not a drawn one
        (f"abc\n{LINK}, tail", (0, 0), ("d", "f", ","), " tail"),
        (f"{LINK}, tail\nzz", (1, 1), ("d", "F", ","), f"{LINK}z"),
        # A line break at the end of a rendered row
        (f"{LINK} tail\nb", (1, 0), ("d", "d"), f"{LINK} tail"),
        (f"{LINK} tail\nb\nc", (1, 0), ("d", "l"), f"{LINK} tail"),
        (f"a\n{LINK} tail\nb", (0, 0), ("d", "l"), "b"),
        # On the raw row itself, the address is text like any other
        (f"{LINK} tail", (0, 1), ("d", "w"), "[](http://c.d) tail"),
        (f"{LINK} tail", (0, 1), ("x",), "[](http://c.d) tail"),
    ],
)
async def test_a_delete_reads_stored_columns_on_rendered_rows_too(text, at, keys, after):
    async with run_pilot() as pilot:
        screen = await note_of(pilot, text, at)

        await pilot.press(*keys)

        assert screen.editor.text == after


async def test_after_a_delete_only_the_cursor_line_is_raw():
    async with run_pilot() as pilot:
        screen = await note_of(pilot, f"a\n{LINK}\nb\n{LINK}\nc", (0, 0))
        editor = screen.editor

        await pilot.press("d", "l")

        assert editor.text == f"b\n{LINK}\nc"
        assert editor.cursor_location == (0, 0)
        assert isinstance(editor.document, FoldedDocument)
        assert editor.document.raw_rows == range(1)
        assert editor.document[1] != LINK


async def test_a_delete_up_from_the_bottom_of_a_long_note_leaves_the_view_in_it():
    async with run_pilot() as pilot:
        screen = await note_of(pilot, "\n".join(f"line {n}" for n in range(100)))
        editor = screen.editor

        await pilot.press("G")
        await pilot.pause()
        assert editor.scroll_offset.y > 0

        await pilot.press("d", "g", "g")
        await pilot.pause()

        assert editor.text == ""
        assert editor.cursor_location == (0, 0)
        assert editor.scroll_offset.y == 0


@pytest.mark.parametrize(
    "text, at, keys, after",
    [
        # dd anywhere in the list
        ("1. a\n2. b\n3. c", (1, 0), ("d", "d"), "1. a\n2. c"),
        ("1. a\n2. b\n3. c", (0, 0), ("d", "d"), "1. b\n2. c"),
        ("1. a\n2. b\n3. c", (2, 0), ("d", "d"), "1. a\n2. b"),
        ("1. a\n2. b\n3. c\n4. d", (0, 0), ("2", "d", "d"), "1. c\n2. d"),
        # A list opening on another number keeps opening on it
        ("5. a\n6. b\n7. c", (0, 0), ("d", "d"), "5. b\n6. c"),
        # Quoted, and nested
        ("> 1. a\n> 2. b", (0, 0), ("d", "d"), "> 1. b"),
        ("1. a\n  1. x\n  2. y\n2. b", (1, 0), ("d", "d"), "1. a\n  1. y\n2. b"),
        ("1. a\n  1. x\n2. b", (0, 0), ("d", "d"), "  1. x\n1. b"),
        # The line between two lists goes: they're one list
        ("1. a\n\n1. b", (1, 0), ("d", "d"), "1. a\n2. b"),
        # Text before the list has nothing to do with its numbers
        ("x\n1. a\n2. b", (0, 0), ("d", "d"), "1. a\n2. b"),
        ("x\n1. a\n2. b", (1, 0), ("d", "d"), "x\n1. b"),
        # Nor does a separate list below what went take over the deleted one's
        ("1. a\n\n5. b\n6. c", (0, 0), ("2", "d", "d"), "5. b\n6. c"),
        ("3. a\nplain\n1. b\n2. c", (0, 0), ("2", "d", "d"), "1. b\n2. c"),
        ("1. a\nplain\n- x\n7. b", (0, 0), ("3", "d", "d"), "7. b"),
        # A bullet takes over no number
        ("- a\n1. b\n2. c", (0, 0), ("d", "d"), "1. b\n2. c"),
        # Edits on a marker are literal, then the numbers are put right
        ("1. a\n12. b\n13. c", (1, 1), ("x",), "1. a\n2. b\n3. c"),
        ("1. a\n2. b", (1, 1), ("x",), "1. a\n2 b"),
        ("1. a\n2. b", (0, 0), ("x",), ". a\n2. b"),
        ("1. a\n2. b\n3. c", (1, 0), ("D",), "1. a\n\n3. c"),
        ("1. a\n2. b", (0, 0), ("d", "w"), ". a\n2. b"),
        ("- a", (0, 0), ("x",), " a"),
        # The rest of the items' text is plain text
        ("1. abc\n2. d", (0, 3), ("x",), "1. bc\n2. d"),
    ],
)
async def test_deleting_from_a_list_counts_it_again(text, at, keys, after):
    async with run_pilot() as pilot:
        screen = await note_of(pilot, text, at)

        await pilot.press(*keys)

        assert screen.editor.text == after


async def test_a_delete_works_in_the_pinned_note_too():
    async with run_pilot() as pilot:
        app = await boot(pilot)
        PinnedNote.set_text("foo bar")

        app.push_screen(PinnedNoteScreen())
        await pilot.pause()

        await pilot.press("d", "w")
        await pilot.press("escape")
        await pilot.pause()

        assert PinnedNote.get_text() == "bar"


async def test_the_attachment_strip_keeps_its_own_x():
    async with run_pilot() as pilot:
        screen = await note_of(pilot, "abc")
        screen.attach([__file__])
        await pilot.press("g", "f")
        await pilot.pause()

        await pilot.press("x", "x")
        await pilot.pause()

        assert screen.editor.text == "abc"
        assert not screen.files.paths


# --- Into INSERT, and the change operator --------------------------------------


@pytest.mark.parametrize(
    "text, at, keys, typed, after",
    [
        ("abc", (0, 1), ("i",), "X", "aXbc"),
        ("abc", (0, 1), ("a",), "X", "abXc"),
        ("abc", (0, 2), ("a",), "X", "abcX"),
        ("  abc", (0, 4), ("I",), "X", "  Xabc"),
        ("  abc", (0, 0), ("A",), "X", "  abcX"),
        ("foo\nbar", (0, 1), ("o",), "X", "foo\nX\nbar"),
        ("foo\nbar", (1, 1), ("O",), "X", "foo\nX\nbar"),
        ("- foo", (0, 0), ("o",), "X", "- foo\n- X"),
        ("- foo", (0, 0), ("O",), "X", "- X\n- foo"),
        ("> - foo", (0, 0), ("o",), "X", "> - foo\n> - X"),
        # A numbered list is counted again, with the cursor still on the new item
        ("3. foo", (0, 0), ("o",), "X", "3. foo\n4. X"),
        ("1. a\n2. b", (0, 0), ("o",), "X", "1. a\n2. X\n3. b"),
        ("1. a\n2. b", (1, 0), ("O",), "X", "1. a\n2. X\n3. b"),
        ("1. a\n2. b", (0, 0), ("O",), "X", "1. X\n2. a\n3. b"),
        ("9. a", (0, 0), ("o",), "X", "9. a\n10. X"),
        # `c`, with the rest of the line kept
        ("foo bar", (0, 0), ("c", "w"), "X", "X bar"),
        ("foo bar", (0, 1), ("c", "w"), "X", "fX bar"),
        ("foo bar", (0, 4), ("c", "w"), "X", "foo X"),
        ("foo, bar", (0, 0), ("c", "t", ","), "X", "X, bar"),
        ("foo bar", (0, 4), ("C",), "X", "foo X"),
        ("- foo", (0, 3), ("c", "c"), "X", "- X"),
        ("  - foo", (0, 5), ("c", "c"), "X", "  - X"),
        ("1. a\n2. foo", (1, 4), ("c", "c"), "X", "1. a\n2. X"),
        ("> foo", (0, 3), ("c", "c"), "X", "> X"),
        ("- a\n- b\n- c", (0, 0), ("2", "c", "c"), "X", "- X\n- c"),
        ("1. a\n2. b\n3. c", (0, 0), ("2", "c", "c"), "X", "1. X\n2. c"),
        ("1. a\n2. b", (0, 0), ("c", "l"), "X", "1. X"),
        # At a line's end, where NORMAL couldn't have put the cursor
        ("abc", (0, 2), ("c", "ö"), "X", "abX"),
    ],
)
async def test_entering_insert_and_typing(text, at, keys, typed, after):
    async with run_pilot() as pilot:
        screen = await note_of(pilot, text, at)

        await pilot.press(*keys)
        assert screen.editor.mode == MODE_INSERT

        await pilot.press(*typed)
        assert screen.editor.text == after

        await pilot.press("escape")
        assert screen.editor.mode == MODE_NORMAL
        assert screen.editor.text == after


async def test_the_cursor_of_a_change_on_a_folded_link_is_a_stored_one():
    text = "first\n- see [name](https://example.com/long) now"

    async with run_pilot() as pilot:
        screen = await note_of(pilot, text)

        await pilot.press("l", "c", "c")
        assert screen.editor.text == "first\n- "
        assert screen.editor.cursor_location == (1, 2)

        await pilot.press("X")
        assert screen.editor.text == "first\n- X"


async def test_opening_a_line_by_a_folded_link_leaves_the_link_whole():
    text = "[name](https://example.com/long)\nbelow"

    async with run_pilot() as pilot:
        screen = await note_of(pilot, text, (1, 0))

        await pilot.press("O", "X")

        assert screen.editor.text == "[name](https://example.com/long)\nX\nbelow"


async def test_o_opens_no_links_any_more():
    opened: list = []

    async with run_pilot() as pilot:
        with links_opened_into(opened):
            screen = await note_of(pilot, "https://example.com/a")

            await pilot.press("o")

            assert opened == []
            assert screen.editor.mode == MODE_INSERT
            assert screen.editor.text == "https://example.com/a\n"


async def test_r_replaces_a_character_and_stays_in_normal():
    async with run_pilot() as pilot:
        screen = await note_of(pilot, "abc", (0, 1))

        await pilot.press("r", "x")
        assert screen.editor.text == "axc"
        assert screen.editor.cursor_location == (0, 1)
        assert screen.editor.mode == MODE_NORMAL

        await pilot.press("r", "space")
        assert screen.editor.text == "a c"

        await pilot.press("r", "ö")
        assert screen.editor.text == "aöc"


async def test_r_on_a_number_counts_the_list_again():
    async with run_pilot() as pilot:
        screen = await note_of(pilot, "1. a\n2. b", (1, 0))

        await pilot.press("r", "7")

        assert screen.editor.text == "1. a\n2. b"


async def test_gi_goes_back_to_where_insert_was_left_until_the_window_closes():
    async with run_pilot() as pilot:
        screen = await note_of(pilot, "foo\nbar\nbaz", (1, 1))

        await pilot.press("i", "X", "escape")
        assert screen.editor.text == "foo\nbXar\nbaz"

        await pilot.press("g", "g")
        assert screen.editor.cursor_location[0] == 0

        await pilot.press("g", "i")
        assert screen.editor.mode == MODE_INSERT
        assert screen.editor.cursor_location == (1, 2)

        await pilot.press("Y")
        assert screen.editor.text == "foo\nbXYar\nbaz"

        await pilot.press("escape", "escape")
        await pilot.pause()

        await pilot.press(" ")
        await pilot.pause()

        again = pilot.app.screen
        assert isinstance(again, NoteScreen)
        again.editor.move_cursor((2, 0))

        await pilot.press("g", "i")
        assert again.editor.cursor_location == (2, 0)


async def test_pending_change_shows_beside_the_chip_and_escape_cancels_it():
    async with run_pilot() as pilot:
        screen = await note_of(pilot, "foo bar")

        await pilot.press("2", "c")
        assert screen.editor.engine.pending == "2c"

        await pilot.press("escape")
        assert screen.editor.engine.pending == ""
        assert screen.editor.mode == MODE_NORMAL
        assert pilot.app.screen is screen


async def test_a_change_works_in_the_pinned_note_too():
    async with run_pilot() as pilot:
        app = await boot(pilot)
        PinnedNote.set_text("foo bar")

        app.push_screen(PinnedNoteScreen())
        await pilot.pause()

        await pilot.press("c", "w", "X", "escape", "escape")
        await pilot.pause()

        assert PinnedNote.get_text() == "X bar"


# --- Undo and redo --------------------------------------------------------------


async def test_u_and_ctrl_r_step_through_commands_in_the_note():
    async with run_pilot() as pilot:
        screen = await note_holding(pilot, "one two\nthree")
        editor = screen.editor

        editor.move_cursor((0, 4))
        await pilot.press("d", "w")
        await pilot.press("l", "x")
        await pilot.pause()
        assert editor.text == "one \nthre"

        await pilot.press("u")
        await pilot.pause()
        assert editor.text == "one \nthree"
        assert editor.mode == MODE_NORMAL

        await pilot.press("u")
        await pilot.pause()
        assert editor.text == "one two\nthree"
        assert editor.cursor_location == (0, 4)
        assert editor.selection == Selection.cursor((0, 4))
        assert editor.mode == MODE_NORMAL

        await pilot.press("ctrl+r", "ctrl+r")
        await pilot.pause()
        assert editor.text == "one \nthre"
        assert editor.mode == MODE_NORMAL


async def test_a_step_can_start_far_from_where_it_edits():
    """Deleting back to a place: the cursor returns to where the command began"""

    async with run_pilot() as pilot:
        screen = await note_holding(pilot, "one\ntwo\nthree")
        editor = screen.editor

        editor.move_cursor((2, 2))
        await pilot.press("d", "g", "g")
        await pilot.pause()
        assert editor.text == ""

        await pilot.press("u")
        await pilot.pause()
        assert editor.text == "one\ntwo\nthree"
        assert editor.cursor_location == (2, 2)


async def test_undo_clears_a_selection():
    async with run_pilot() as pilot:
        screen = await note_holding(pilot, "one two")
        editor = screen.editor

        await pilot.press("x")
        editor.selection = Selection((0, 0), (0, 3))
        await pilot.press("u")
        await pilot.pause()

        assert editor.text == "one two"
        assert editor.selection.is_empty


async def test_a_long_insert_session_is_one_step_whatever_it_does():
    """Upstream splits on time, size, line breaks and cursor moves. None may here"""

    async with run_pilot() as pilot:
        screen = await note_holding(pilot, "start")
        editor = screen.editor
        clock = iter(range(0, 100000, 10))

        with patch.object(editor.history, "_get_time", lambda: float(next(clock))):
            await pilot.press("A")
            await pilot.press(*["z"] * 120)
            await pilot.press("enter", "-", "space", "x", "enter")
            await pilot.press("left", "left", "backspace", "q")
            editor.post_message(events.Blur())
            await pilot.pause()
            await pilot.press("z", "escape")
            await pilot.pause()

        written = editor.text
        assert len(written) > 120

        await pilot.press("u")
        await pilot.pause()
        assert editor.text == "start"
        assert editor.cursor_location == (0, 0)

        await pilot.press("ctrl+r")
        await pilot.pause()
        assert editor.text == written


async def test_the_last_thousand_steps_are_kept():
    text = "x" * 1005

    async with run_pilot() as pilot:
        screen = await open_note(pilot)
        await pilot.press("escape")
        editor = screen.editor
        editor.load_text(text)
        await pilot.pause()

        for _ in range(1001):
            editor.engine.feed("x")

        assert editor.text == "x" * 4

        for _ in range(1100):
            editor.engine.feed("u")

        # The first of the 1001 fell off the end
        assert editor.text == "x" * 1004


@pytest.mark.parametrize("insert", [False, True])
@pytest.mark.parametrize("key", ["ctrl+z", "ctrl+y", "super+z", "super+y"])
async def test_the_desktop_undo_keys_do_nothing_in_a_note(key, insert):
    async with run_pilot() as pilot:
        screen = await note_holding(pilot, "abc")
        editor = screen.editor
        tasks = len(Todo.all())

        await pilot.press("x", "u", "x")
        if insert:
            await pilot.press("i", "!")
        await pilot.pause()
        text = editor.text

        with patch.object(pilot.app.api, "_step_history") as panes_stepped:
            await pilot.press(key)
            await pilot.pause()
            await pilot.pause()

        panes_stepped.assert_not_called()
        assert editor.text == text
        assert pilot.app.screen is screen
        assert editor.mode == (MODE_INSERT if insert else MODE_NORMAL)

        # The panes behind would have taken back the task it's the note of
        assert len(Todo.all()) == tasks


@pytest.mark.parametrize("key", ["ctrl+z", "ctrl+y", "super+z"])
async def test_the_desktop_undo_keys_do_nothing_on_the_files_strip(key):
    async with run_pilot() as pilot:
        screen = await note_holding(pilot, "abc")
        tasks = len(Todo.all())
        screen.attach([__file__])
        await pilot.pause()
        await pilot.press("g", "f")
        await pilot.pause()
        assert screen.picking_files

        with patch.object(pilot.app.api, "_step_history") as panes_stepped:
            await pilot.press(key)
            await pilot.pause()
            await pilot.pause()

        panes_stepped.assert_not_called()
        assert screen.editor.text == "abc"
        assert pilot.app.screen is screen
        assert len(Todo.all()) == tasks


async def test_insert_has_no_undo_key_of_its_own():
    async with run_pilot() as pilot:
        screen = await note_holding(pilot, "abc")

        await pilot.press("i", "u", "ctrl+r")
        await pilot.pause()
        assert screen.editor.text == "uabc"


async def test_undoing_a_delete_brings_a_list_back_with_its_numbers():
    text = "1. one\n2. two\n3. three"

    async with run_pilot() as pilot:
        screen = await open_note(pilot)
        await pilot.press("escape")
        editor = screen.editor
        editor.load_text(text)
        await pilot.pause()

        await pilot.press("d", "d")
        await pilot.pause()
        assert editor.text == "1. two\n2. three"

        await pilot.press("u")
        await pilot.pause()
        assert editor.text == text

        await pilot.press("ctrl+r")
        await pilot.pause()
        assert editor.text == "1. two\n2. three"


async def test_undoing_puts_a_list_back_exactly_as_it_was_counted():
    """Numbers someone left wrong aren't put right by taking a change back"""

    text = "1. one\n7. two"

    async with run_pilot() as pilot:
        screen = await open_note(pilot)
        await pilot.press("escape")
        editor = screen.editor
        editor.load_text(text)
        await pilot.pause()

        await pilot.press("A", "!", "escape")
        await pilot.pause()
        assert editor.text != text

        await pilot.press("u")
        await pilot.pause()
        assert editor.text == text


async def test_a_paste_from_normal_is_one_step_with_its_session():
    set_clipboard("pasted")

    async with run_pilot() as pilot:
        screen = await note_holding(pilot, "abc")
        editor = screen.editor

        await pilot.press("ctrl+v")
        await pilot.pause()
        await pilot.press("!", "escape")
        await pilot.pause()
        assert "pasted!" in editor.text

        await pilot.press("u")
        await pilot.pause()
        assert editor.text == "abc"


async def test_clearing_the_note_can_be_undone():
    async with run_pilot() as pilot:
        screen = await note_holding(pilot, "abc\ndef")
        editor = screen.editor

        await pilot.press("i", "ctrl+d", "y", "escape")
        await pilot.pause()
        assert editor.text == ""

        await pilot.press("u")
        await pilot.pause()
        assert editor.text == "abc\ndef"


async def test_what_undo_leaves_is_what_gets_saved():
    async with run_pilot() as pilot:
        await note_holding(pilot, "kept")

        await pilot.press("x", "u")
        await pilot.press("escape")
        await pilot.pause()

        assert Todo.all()[0].note == "kept"


async def test_a_reopened_note_has_nothing_to_undo():
    async with run_pilot() as pilot:
        await note_holding(pilot, "kept")
        await pilot.press("escape")
        await pilot.pause()

        await pilot.press(" ")
        await pilot.pause()
        screen = pilot.app.screen
        assert isinstance(screen, NoteScreen)

        await pilot.press("u")
        await pilot.pause()
        assert screen.editor.text == "kept"


# ------------------------------------------------------------------
# ------------------------- Search ---------------------------------
# ------------------------------------------------------------------


def hint_text(screen) -> str:
    return str(screen.hint.render())


def lit(editor, y: int, x: int) -> bool:
    return cell(editor, y, x).bgcolor == theme_of(editor)[SEARCH_MATCH].bgcolor


async def test_the_search_prompt_is_in_the_hint_line_and_types_there():
    async with run_pilot() as pilot:
        screen = await note_holding(pilot, "foo bar")
        hints = hint_text(screen)

        await pilot.press("?", "b", "a", "space")
        await pilot.pause()

        assert hint_text(screen).startswith("?ba ")
        assert screen.editor.text == "foo bar"
        assert screen.editor.mode == MODE_NORMAL

        await pilot.press("escape")
        await pilot.pause()
        assert hint_text(screen) == hints


async def test_the_prompt_is_labelled_with_the_key_that_opens_it():
    async with run_pilot() as pilot:
        screen = await note_holding(pilot, "foo")
        pilot.app.api.vim.keys.remap({"?": "/"})

        await pilot.press("/", "f")
        await pilot.pause()

        assert hint_text(screen).startswith("/f")


async def test_typing_markup_in_the_prompt_shows_it_as_typed():
    async with run_pilot() as pilot:
        screen = await note_holding(pilot, "[red] x")

        await pilot.press(*"?[red]")
        await pilot.pause()
        assert hint_text(screen).startswith("?[red]")

        await pilot.press("x", "enter")
        await pilot.pause()
        assert "Not found: [red]x" in hint_text(screen)


async def test_a_backslash_in_the_prompt_shows_as_typed():
    async with run_pilot() as pilot:
        screen = await note_holding(pilot, "a[b")

        await pilot.press(*"?a[", "backslash")
        await pilot.pause()

        assert hint_text(screen).startswith("?a[\\█")

        await pilot.press("enter")
        await pilot.pause()
        assert hint_text(screen).endswith("Not found: a[\\")


async def test_a_rebound_prompt_key_is_written_as_the_hints_write_it():
    async with run_pilot() as pilot:
        screen = await note_holding(pilot, "foo")
        pilot.app.api.vim.keys.remap({"?": "<ctrl+f>"})

        await pilot.press("ctrl+f", "f")
        await pilot.pause()

        assert hint_text(screen).startswith("C-ff")


async def test_a_message_expiring_leaves_the_prompt_standing():
    async with run_pilot() as pilot:
        screen = await note_holding(pilot, "foo")

        await pilot.press("n")
        await pilot.pause()
        assert "No search yet" in hint_text(screen)

        await pilot.press("?", "f")
        await pilot.pause()
        screen.mode_changed()
        await pilot.pause()

        assert hint_text(screen).startswith("?f")


async def test_the_first_match_is_lit_and_scrolled_to_while_typing():
    async with run_pilot() as pilot:
        lines = [f"line {row}" for row in range(60)] + ["needle here"]
        screen = await note_holding(pilot, "\n".join(lines))
        editor = screen.editor
        assert editor.scroll_offset.y == 0

        await pilot.press(*"?need")
        await pilot.pause()

        assert editor.cursor_location == (60, 0)
        assert editor.scroll_offset.y > 0

        y = 60 - editor.scroll_offset.y
        assert lit(editor, y, 1)
        assert not lit(editor, y, 5)


async def test_escape_in_the_prompt_restores_the_cursor_and_keeps_the_note_open():
    async with run_pilot() as pilot:
        screen = await note_holding(pilot, "abc\ndef\nghi")
        editor = screen.editor
        editor.move_cursor((1, 1))

        await pilot.press("?", "g", "h")
        await pilot.pause()
        assert editor.cursor_location == (2, 0)

        await pilot.press("escape")
        await pilot.pause()

        assert pilot.app.screen is screen
        assert editor.cursor_location == (1, 1)
        assert not lit(editor, 2, 1)


async def test_enter_confirms_and_the_highlights_stay_as_the_cursor_moves_off():
    async with run_pilot() as pilot:
        screen = await note_holding(pilot, "aa foo\nbar\nfoo")
        editor = screen.editor

        await pilot.press(*"?foo", "enter")
        await pilot.pause()
        assert editor.cursor_location == (0, 3)
        assert screen.editor.engine.search_prompt is None

        await pilot.press("l")
        await pilot.pause()

        assert editor.cursor_location[0] == 1
        assert lit(editor, 0, 3)
        assert lit(editor, 2, 2)
        assert not lit(editor, 0, 0)


async def test_escape_clears_highlights_first_and_closes_the_note_after():
    async with run_pilot() as pilot:
        screen = await note_holding(pilot, "foo\nbar\nfoo")
        editor = screen.editor

        await pilot.press(*"?foo", "enter", "l")
        await pilot.pause()
        assert lit(editor, 0, 0)

        await pilot.press("escape")
        await pilot.pause()
        assert pilot.app.screen is screen
        assert not lit(editor, 0, 0)

        await pilot.press("escape")
        await pilot.pause()
        assert pilot.app.screen is not screen


async def test_highlights_land_on_the_drawn_text_of_a_folded_line():
    async with run_pilot() as pilot:
        screen = await note_holding(pilot, "[name](http://example.com) tail\n\nx")
        editor = screen.editor
        await pilot.press("G")
        await pilot.pause()

        await pilot.press(*"?tail", "enter")
        await pilot.pause()
        await pilot.press("G")
        await pilot.pause()

        # Drawn as `name tail`: the address takes up no room
        document = editor.document
        assert isinstance(document, FoldedDocument)
        assert document[0] == "name tail"
        assert lit(editor, 0, 5)
        assert lit(editor, 0, 8)
        assert not lit(editor, 0, 4)


async def test_a_match_in_a_hidden_address_shows_only_once_the_line_is_raw():
    async with run_pilot() as pilot:
        stored = "[name](http://example.com) tail"
        screen = await note_holding(pilot, "first\n\n" + stored)
        editor = screen.editor

        await pilot.press(*"?example")
        await pilot.pause()

        document = editor.document
        assert isinstance(document, FoldedDocument)
        assert editor.cursor_location == (2, stored.index("example"))
        assert document[2] == stored
        assert lit(editor, 2, stored.index("example") + 1)

        # Off the line it folds, and what's matched goes with the address
        await pilot.press("enter", "g", "g")
        await pilot.pause()

        assert document[2] == "name tail"
        assert not any(lit(editor, 2, x) for x in range(9))


async def test_highlights_follow_an_edit():
    async with run_pilot() as pilot:
        screen = await note_holding(pilot, "foo bar")
        editor = screen.editor

        await pilot.press(*"?bar", "enter", "=", "i", "x")
        await pilot.pause()

        assert editor.text == "xfoo bar"
        assert lit(editor, 0, 5)
        assert not lit(editor, 0, 4)


async def test_highlights_follow_an_undo_and_a_redo():
    async with run_pilot() as pilot:
        screen = await note_holding(pilot, "xx foo")
        editor = screen.editor

        await pilot.press(*"?foo", "enter", "=", "d", "w")
        await pilot.pause()
        assert editor.text == "foo"
        assert lit(editor, 0, 1)

        await pilot.press("u")
        await pilot.pause()
        assert editor.text == "xx foo"
        assert lit(editor, 0, 4)
        assert not lit(editor, 0, 1)

        await pilot.press("ctrl+r")
        await pilot.pause()
        assert editor.text == "foo"
        assert lit(editor, 0, 1)


async def test_searching_leaves_nothing_to_undo():
    async with run_pilot() as pilot:
        screen = await note_holding(pilot, "foo bar")
        editor = screen.editor

        await pilot.press("x")
        await pilot.press(*"?bar", "enter", "n", "*")
        await pilot.press("u")
        await pilot.pause()

        assert editor.text == "foo bar"


async def test_a_character_jump_shows_over_the_highlights_and_gives_them_back():
    async with run_pilot() as pilot:
        screen = await note_holding(pilot, "foo bar\nfoo")
        editor = screen.editor

        await pilot.press(*"?foo", "enter", "g", "g")
        await pilot.pause()
        assert lit(editor, 1, 0)

        await pilot.press("f", "r")
        await pilot.pause()
        assert cell(editor, 1, 0).color == theme_of(editor)[BACKDROP].color

        await pilot.press("escape")
        await pilot.pause()
        assert pilot.app.screen is screen
        assert lit(editor, 1, 0)


async def test_n_and_big_n_say_when_they_wrap_in_the_hint_line():
    async with run_pilot() as pilot:
        screen = await note_holding(pilot, "foo x foo")
        editor = screen.editor

        await pilot.press(*"?foo", "enter", "n")
        await pilot.pause()
        assert editor.cursor_location == (0, 0)
        assert "wrapped to the top" in hint_text(screen)

        await pilot.press("N")
        await pilot.pause()
        assert editor.cursor_location == (0, 6)
        assert "wrapped to the bottom" in hint_text(screen)


async def test_n_with_no_search_yet_says_so_in_the_hint_line():
    async with run_pilot() as pilot:
        screen = await note_holding(pilot, "foo")

        await pilot.press("N")
        await pilot.pause()

        assert "No search yet" in hint_text(screen)


async def test_star_searches_the_word_under_the_cursor():
    async with run_pilot() as pilot:
        screen = await note_holding(pilot, "Foo foobar foo")
        editor = screen.editor

        await pilot.press("*")
        await pilot.pause()

        assert editor.cursor_location == (0, 11)
        assert lit(editor, 0, 0)
        assert not lit(editor, 0, 4)


async def test_the_last_search_lasts_into_another_note_with_nothing_lit_there():
    async with run_pilot() as pilot:
        screen = await note_holding(pilot, "foo foo")
        await pilot.press(*"?foo", "enter", "escape", "escape")
        await pilot.pause()
        assert pilot.app.screen is not screen

        await pilot.press(" ")
        await pilot.pause()
        again = pilot.app.screen
        assert isinstance(again, NoteScreen) and again is not screen
        assert not lit(again.editor, 0, 0)

        again.editor.move_cursor((0, 0))
        await pilot.press("n")
        await pilot.pause()

        assert again.editor.cursor_location == (0, 4)
        assert lit(again.editor, 0, 0)


async def test_a_paste_doesnt_write_into_the_note_during_the_prompt():
    async with run_pilot() as pilot:
        screen = await note_holding(pilot, "foo")
        editor = screen.editor

        await pilot.press("?")
        await editor._on_paste(events.Paste("pasted"))
        await pilot.pause()

        assert editor.text == "foo"
        assert editor.mode == MODE_NORMAL
        assert editor.engine.search_prompt == ""


async def test_the_pinned_note_searches_too():
    async with run_pilot() as pilot:
        app = await boot(pilot)
        PinnedNote.set_text("abc abc")
        app.push_screen(PinnedNoteScreen())
        await pilot.pause()

        await pilot.press(*"?abc", "enter")
        await pilot.pause()

        screen = app.screen
        assert isinstance(screen, PinnedNoteScreen)
        assert screen.editor.cursor_location == (0, 4)


# --- Yank and paste -----------------------------------------------------------


async def test_yyp_duplicates_a_line_and_u_takes_it_back():
    set_clipboard("")

    async with run_pilot() as pilot:
        screen = await note_holding(pilot, "abc\ndef")
        editor = screen.editor

        await pilot.press("y", "y", "p")
        await pilot.pause()

        assert editor.text == "abc\nabc\ndef"
        assert editor.cursor_location == (1, 0)
        assert editor.mode == MODE_NORMAL

        await pilot.press("u")
        await pilot.pause()
        assert editor.text == "abc\ndef"


async def test_y_reaches_the_system_clipboard_but_d_does_not():
    set_clipboard("")

    async with run_pilot() as pilot:
        await note_holding(pilot, "abc def\nghi")

        await pilot.press("y", "e")
        await pilot.pause()
        assert pilot.app.clipboard == "abc"

        with patch("todooit.utils.clipboard.pyperclip.copy") as copied:
            await pilot.press("d", "w", "x", "c", "c", "escape")
            await pilot.pause()

        copied.assert_not_called()
        assert pilot.app.clipboard == "abc"


async def test_p_prefers_a_clipboard_changed_since_the_yank():
    set_clipboard("")

    async with run_pilot() as pilot:
        screen = await note_holding(pilot, "abc")
        editor = screen.editor

        await pilot.press("y", "y")
        await pilot.pause()

        # What the yank put there, as a real clipboard would hand it back
        set_clipboard("abc")
        await pilot.press("p")
        await pilot.pause()
        assert editor.text == "abc\nabc"

        set_clipboard("from a browser")
        await pilot.press("P")
        await pilot.pause()

        assert editor.text == "abc\nfrom a browserabc"
        assert editor.mode == MODE_NORMAL
        assert editor.cursor_location == (1, len("from a browser") - 1)

        await pilot.press("u")
        await pilot.pause()
        assert editor.text == "abc\nabc"


async def test_p_reads_the_clipboard_as_markdown_as_the_paste_path_does():
    set_clipboard("* one\n* two")

    async with run_pilot() as pilot:
        screen = await note_holding(pilot, "")
        editor = screen.editor

        await pilot.press("p")
        await pilot.pause()

        assert editor.text == "- one\n- two"
        assert editor.mode == MODE_NORMAL


async def test_p_makes_a_long_bare_url_a_link():
    url = "https://example.com/" + "long-path/" * 12
    set_clipboard(url)

    async with run_pilot() as pilot:
        screen = await note_holding(pilot, "")

        await pilot.press("p")
        await pilot.pause()

        assert screen.editor.text == f"[]({url})"

        await pilot.press("p")
        await pilot.pause()

        # The same paste again comes out the same, not as the bare address
        assert screen.editor.text.count(f"]({url})") == 2


async def test_p_always_pastes_text_while_ctrl_v_attaches_files():
    set_clipboard("/tmp/some-file.txt")

    async with run_pilot() as pilot:
        screen = await note_holding(pilot, "")
        editor = screen.editor

        with patch.object(screen, "attach") as attach:
            await pilot.press("p")
            await pilot.pause()

            attach.assert_not_called()
            assert editor.text == "/tmp/some-file.txt"

            await pilot.press("ctrl+v")
            await pilot.pause()

            attach.assert_called_once_with(["/tmp/some-file.txt"])


async def test_p_never_looks_for_a_copied_file():
    set_clipboard("")

    async with run_pilot() as pilot:
        await note_holding(pilot, "abc")

        with patch("todooit.ui.screens.note.vim.clipboard.paste_files") as files:
            await pilot.press("p")
            await pilot.pause()

        files.assert_not_called()


async def test_yyp_renumbers_a_list():
    set_clipboard("")

    async with run_pilot() as pilot:
        screen = await note_holding(pilot, "1. a\nb")
        editor = screen.editor
        assert editor.text == "1. a\n2. b"

        await pilot.press("y", "y", "p")
        await pilot.pause()

        assert editor.text == "1. a\n2. a\n3. b"


async def test_a_yank_in_one_note_pastes_in_another():
    set_clipboard("")

    async with run_pilot() as pilot:
        await note_holding(pilot, "carried over")
        await pilot.press("y", "y")
        await pilot.pause()

        # What the yank put on the clipboard
        set_clipboard("carried over")

        await pilot.press("escape")
        await pilot.pause()

        app = pilot.app
        PinnedNote.set_text("pinned")
        app.push_screen(PinnedNoteScreen())
        await pilot.pause()

        screen = app.screen
        assert isinstance(screen, PinnedNoteScreen)
        await pilot.press("p")
        await pilot.pause()

        assert screen.editor.text == "pinned\ncarried over"
