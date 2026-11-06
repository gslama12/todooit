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
from todooit.ui.screens.note.disp.markup import BACKDROP, TARGET
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

        pilot.app.api.vim.keys.remap({"j": "a"})
        screen.mode_changed()

        assert "aö/kl move" in str(screen.hint.render())


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


@pytest.mark.parametrize("key", ["u", "d", "o", "0", "$"])
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
            {"i": "a", "<ctrl+u>": "<ctrl+b>", "<ctrl+d>": "<ctrl+f>", "gx": "gl"}
        )
        screen.mode_changed()

        hint = str(screen.hint.render())
        for shown in ("a insert", "C-b/C-f half page", "gl link"):
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
