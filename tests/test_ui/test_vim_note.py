"""
The vim engine at work in the note window: the adapter, the keymap and the modes
"""

from textual.geometry import Offset
from textual.widgets.text_area import Selection

from tests.test_ui.test_note_ui import open_note
from tests.test_ui.ui_base import boot, commit_line, create_and_move_to_todo, run_pilot
from todooit.api import PinnedNote, Todo
from todooit.ui.screens.note import NoteScreen, NoteScreenBase, PinnedNoteScreen
from todooit.ui.screens.note.vim.modes import MODE_INSERT, MODE_NORMAL
from todooit.vim_engine import VimMotion


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

        pilot.app.api.vim.keys.remap({"ö": "w"})

        await pilot.press("w")
        assert editor.cursor_location == (0, 1)

        await pilot.press("ö")
        assert editor.cursor_location == (0, 1)


async def test_the_note_does_not_follow_the_panes_direction_keys():
    async with run_pilot() as pilot:
        screen = await note_holding(pilot, "abc\ndef")
        editor = screen.editor

        pilot.app.api.keys.remap({"ö": "w", "l": "b"})
        assert pilot.app.api.motion_keys().right == "w"

        await pilot.press("w")
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

        await pilot.press("$")
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


async def test_a_motion_between_two_gs_does_not_make_a_gg():
    async with run_pilot() as pilot:
        screen = await note_holding(pilot, "abc\ndef")
        editor = screen.editor
        editor.move_cursor((1, 1))

        await pilot.press("g", "j", "g")

        assert editor.cursor_location == (1, 0)
