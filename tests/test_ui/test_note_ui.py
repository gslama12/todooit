"""
Notes: the window on a todo's note, and the pinned scratchpad
"""

from unittest.mock import patch

from rich.cells import cell_len

from todooit.api import PinnedNote, Todo
from todooit.api.theme import DooitThemeBase
from todooit.ui.screens.note import (
    EMPH,
    EMPH_MARK,
    HEADER,
    MARKER,
    MODE_INSERT,
    MODE_NORMAL,
    QUOTE,
    QUOTE_BAR,
    QUOTE_GLYPH,
    RULE,
    RULE_SPAN,
    NoteScreen,
    NoteScreenBase,
    build_theme,
    scan_note,
)
from todooit.ui.screens.pinned_note import PinnedNoteScreen
from tests.test_ui.ui_base import (
    boot,
    commit_line,
    create_and_move_to_todo,
    run_pilot,
)


async def open_note(pilot, description: str = "task with a note") -> NoteScreen:
    """A project, a todo, and the note window opened on it with space"""

    await create_and_move_to_todo(pilot)
    await pilot.press("n")
    await commit_line(pilot, description)

    await pilot.press(" ")
    await pilot.pause()

    screen = pilot.app.screen
    assert isinstance(screen, NoteScreen)
    return screen


async def test_space_opens_the_note_window():
    async with run_pilot() as pilot:
        screen = await open_note(pilot, "the todo")

        # Titled by the todo, and opened ready to write: there is nothing in
        # an empty note to have opened it to read
        assert screen.editor.border_title == "the todo"
        assert screen.editor.mode == MODE_INSERT


async def test_a_written_note_opens_to_be_read():
    async with run_pilot() as pilot:
        screen = await open_note(pilot)

        await pilot.press(*list("something written"))
        await pilot.press("escape", "escape")
        await pilot.pause()

        # Second time round there is something on the page, so it opens in
        # NORMAL and the letters are motions again
        await pilot.press(" ")
        await pilot.pause()

        screen = pilot.app.screen
        assert isinstance(screen, NoteScreen)
        assert screen.editor.mode == MODE_NORMAL


async def test_writing_a_note_and_closing_saves_it():
    async with run_pilot() as pilot:
        app = pilot.app
        screen = await open_note(pilot)

        assert screen.editor.mode == MODE_INSERT
        await pilot.press(*list("remember the milk"))
        await pilot.press("escape")  # back to NORMAL
        assert screen.editor.mode == MODE_NORMAL

        await pilot.press("escape")  # close the window
        await pilot.pause()

        assert not isinstance(app.screen, NoteScreenBase)
        assert Todo.all()[0].note == "remember the milk"


async def test_the_note_opens_on_what_it_holds():
    async with run_pilot() as pilot:
        screen = await open_note(pilot)

        await pilot.press(*list("first draft"))
        await pilot.press("escape", "escape")
        await pilot.pause()

        # Open it again: the text is there, and typing continues it
        await pilot.press(" ")
        await pilot.pause()

        screen = pilot.app.screen
        assert isinstance(screen, NoteScreen)
        assert screen.editor.text == "first draft"

        await pilot.press("A")  # insert at the end of the line
        await pilot.press(*list(" and more"))
        await pilot.press("escape", "escape")
        await pilot.pause()

        assert Todo.all()[0].note == "first draft and more"


async def test_normal_mode_letters_do_not_write():
    async with run_pilot() as pilot:
        app = pilot.app
        await open_note(pilot)

        await pilot.press("escape")  # an empty note opens in INSERT
        await pilot.press(*list("kjl"))  # motions, not letters
        await pilot.press("escape")
        await pilot.pause()

        assert not isinstance(app.screen, NoteScreenBase)
        assert Todo.all()[0].note == ""


async def test_clear_note_asks_first():
    async with run_pilot() as pilot:
        screen = await open_note(pilot)

        await pilot.press(*list("precious words"))
        await pilot.press("escape")

        await pilot.press("ctrl+d")
        await pilot.pause()
        assert screen.awaiting_clear

        # Anything but y leaves the note exactly where it is
        await pilot.press("n")
        await pilot.pause()
        assert not screen.awaiting_clear
        assert screen.editor.text == "precious words"

        await pilot.press("ctrl+d")
        await pilot.press("y")
        await pilot.pause()

        assert screen.editor.text == ""

        await pilot.press("escape")
        await pilot.pause()
        assert Todo.all()[0].note == ""


async def test_note_marks_the_row():
    """The paper icon: a row with a note is told apart from one without"""

    async with run_pilot() as pilot:
        app = pilot.app
        await create_and_move_to_todo(pilot)
        await pilot.press("n")
        await commit_line(pilot, "plain")

        formatter = app.api.formatter.todos.note
        todo = Todo.all()[0]

        assert formatter.format_value(todo.note, todo).plain.strip() == ""

        todo.note = "something"
        todo.save()

        assert formatter.format_value(todo.note, todo).plain.strip() != ""


async def test_emph_and_bullet_markup():
    async with run_pilot() as pilot:
        screen = await open_note(pilot)

        await pilot.press(*list("word"))

        # Select the line and mark it up as emphasis
        await pilot.press("ctrl+a", "ctrl+e")
        assert screen.editor.text == EMPH_MARK + "word" + EMPH_MARK

        # A bullet goes at the head of the line
        await pilot.press("ctrl+l")
        assert screen.editor.text == "• " + EMPH_MARK + "word" + EMPH_MARK

        # And comes off it again
        await pilot.press("ctrl+l")
        assert screen.editor.text == EMPH_MARK + "word" + EMPH_MARK

        # The same key takes the emphasis off again
        await pilot.press("ctrl+a", "ctrl+e")
        assert screen.editor.text == "word"

        await pilot.press("escape", "escape")
        await pilot.pause()


async def test_emph_marks_take_no_room_on_the_line():
    """What the heading gets for free, emphasis gets from a zero-width mark"""

    assert cell_len(EMPH_MARK) == 0

    line = "say " + EMPH_MARK + "this" + EMPH_MARK + " twice"

    assert cell_len(line) == len("say this twice")


async def test_emph_is_drawn_in_its_own_color():
    line = "say " + EMPH_MARK + "this" + EMPH_MARK + " twice"
    spans = list(scan_note([line]))[0]

    assert (EMPH, "this") in [
        (name, line.encode()[start:end].decode()) for start, end, name in spans
    ]


async def test_emph_toggles_off_a_selection_made_by_eye():
    """The marks cannot be seen, so they are never in what is picked out"""

    async with run_pilot() as pilot:
        screen = await open_note(pilot)

        await pilot.press(*list("one two"))

        # Pick "two" out and emphasise it
        await pilot.press("shift+left", "shift+left", "shift+left")
        await pilot.press("ctrl+e")
        assert screen.editor.text == "one " + EMPH_MARK + "two" + EMPH_MARK

        # The same three letters, and the key takes the marks back out
        await pilot.press("ctrl+e")
        assert screen.editor.text == "one two"

        await pilot.press("escape", "escape")
        await pilot.pause()


async def test_markdown_stars_still_read_as_emphasis():
    """Anything written before the mark went zero-width goes on working"""

    spans = list(scan_note(["old *style* text"]))[0]

    assert EMPH in [name for _, _, name in spans]


async def test_star_markers_are_painted_out():
    """A `*` has already cost a column; the least it can do is not be seen"""

    theme = build_theme(DooitThemeBase)

    assert theme.syntax_styles[MARKER].color.triplet == theme.base_style.bgcolor.triplet


async def test_typing_a_quote_marker():
    async with run_pilot() as pilot:
        screen = await open_note(pilot)

        # markdown's `> ` goes in, the bar it stands for comes out
        await pilot.press(*list("> "))
        assert screen.editor.text == QUOTE_GLYPH

        await pilot.press(*list("a note to self"))
        assert screen.editor.text == QUOTE_GLYPH + "a note to self"

        # Enter carries the bar on, the way it carries a bullet on
        await pilot.press("enter")
        await pilot.press(*list("and another"))
        assert screen.editor.text == (
            QUOTE_GLYPH + "a note to self\n" + QUOTE_GLYPH + "and another"
        )

        # And an empty one is where the quote ends
        await pilot.press("enter", "enter")
        assert screen.editor.text == (
            QUOTE_GLYPH + "a note to self\n" + QUOTE_GLYPH + "and another\n"
        )

        await pilot.press("escape", "escape")
        await pilot.pause()


async def test_ctrl_b_quotes_a_written_line():
    async with run_pilot() as pilot:
        screen = await open_note(pilot)

        await pilot.press(*list("already written"))
        await pilot.press("ctrl+b")
        assert screen.editor.text == QUOTE_GLYPH + "already written"

        # And takes it back out again
        await pilot.press("ctrl+b")
        assert screen.editor.text == "already written"

        await pilot.press("escape", "escape")
        await pilot.pause()


async def test_a_quoted_line_is_green_behind_its_bar():
    line = QUOTE_GLYPH + "a snippet worth keeping"
    names = [name for _, _, name in list(scan_note([line]))[0]]

    assert names == [QUOTE, QUOTE_BAR]


async def test_a_quote_still_holds_markup():
    """A quoted line is still a line of the note: links and emphasis work"""

    emphasised = EMPH_MARK + "this" + EMPH_MARK
    line = QUOTE_GLYPH + "see " + emphasised + " at https://example.com"
    names = [name for _, _, name in list(scan_note([line]))[0]]

    assert names[:2] == [QUOTE, QUOTE_BAR]
    assert EMPH in names


async def test_tab_nests_a_bullet():
    async with run_pilot() as pilot:
        screen = await open_note(pilot)

        await pilot.press("ctrl+l")
        await pilot.press(*list("top"))

        # Enter carries the bullet on, tab takes the new one a level in - and
        # the glyph changes with it, so the depth is readable without counting
        await pilot.press("enter")
        await pilot.press(*list("child"))
        await pilot.press("tab")
        assert screen.editor.text == "• top\n  ◦ child"

        # A second level in, and the glyph changes again
        await pilot.press("tab")
        assert screen.editor.text == "• top\n    ▪ child"

        # And back out the way it came
        await pilot.press("shift+tab", "shift+tab")
        assert screen.editor.text == "• top\n• child"

        await pilot.press("escape", "escape")
        await pilot.pause()

        assert Todo.all()[0].note == "• top\n• child"


async def test_tab_indents_a_plain_line_too():
    """Nesting is what tab is mostly for, but plain text indents as well"""

    async with run_pilot() as pilot:
        screen = await open_note(pilot)

        await pilot.press(*list("plain"))
        await pilot.press("tab")
        assert screen.editor.text == "  plain"

        # The cursor keeps its place in the words rather than its column
        await pilot.press(*list(" words"))
        assert screen.editor.text == "  plain words"

        await pilot.press("shift+tab")
        assert screen.editor.text == "plain words"

        # And no further out than the margin
        await pilot.press("shift+tab")
        assert screen.editor.text == "plain words"

        await pilot.press("escape", "escape")
        await pilot.pause()


async def test_nested_bullets_are_drawn_by_depth():
    lines = ["• top", "  ◦ nested", "    ▪ deeper"]
    names = [[name for _, _, name in row] for row in scan_note(lines)]

    assert names == [["note-bullet-0"], ["note-bullet-1"], ["note-bullet-2"]]


async def test_tab_never_writes_in_normal_mode():
    """The bug: a bare key that edits the note is what NORMAL is for not having"""

    async with run_pilot() as pilot:
        screen = await open_note(pilot)

        await pilot.press(*list("untouched"))
        await pilot.press("escape")
        assert screen.editor.mode == MODE_NORMAL

        await pilot.press("tab", "shift+tab")
        await pilot.pause()

        assert screen.editor.text == "untouched"
        assert screen.editor.mode == MODE_NORMAL

        await pilot.press("escape")
        await pilot.pause()

        assert Todo.all()[0].note == "untouched"


async def test_three_dashes_become_the_separator():
    async with run_pilot() as pilot:
        screen = await open_note(pilot)

        await pilot.press(*list("above"))
        await pilot.press("enter")
        await pilot.press(*list("---"))
        await pilot.pause()

        lines = screen.editor.text.splitlines()
        assert lines[0] == "above"

        # A blank line is kept above it: a rule tight under words is a header,
        # and `ctrl+t` is the key for meaning that
        assert lines[1] == ""
        assert set(lines[2]) == {RULE}

        # The cursor comes to rest on the rule, ready to carry on beneath it
        await pilot.press("enter")
        await pilot.press(*list("below"))
        assert screen.editor.text.splitlines()[3] == "below"

        await pilot.press("escape", "escape")
        await pilot.pause()


async def test_three_dashes_with_nothing_above_need_no_blank_line():
    async with run_pilot() as pilot:
        screen = await open_note(pilot)

        await pilot.press(*list("---"))
        await pilot.pause()

        assert set(screen.editor.text) == {RULE}

        await pilot.press("escape", "escape")
        await pilot.pause()


async def test_a_separator_is_not_a_header():
    """A rule with words over it titles them; one with a blank line does not"""

    header = [name for row in scan_note(["Title", RULE * 5]) for _, _, name in row]
    separator = [name for row in scan_note(["", RULE * 5]) for _, _, name in row]

    assert header == [HEADER, RULE_SPAN]
    assert separator == [RULE_SPAN]


async def test_header_draws_a_rule_under_the_line():
    async with run_pilot() as pilot:
        screen = await open_note(pilot)

        await pilot.press(*list("Section"))
        await pilot.press("ctrl+t")
        await pilot.pause()

        lines = screen.editor.text.splitlines()
        assert lines[0] == "Section"
        assert set(lines[1]) == {RULE}

        # The same key takes the rule away again
        await pilot.press("ctrl+t")
        assert screen.editor.text == "Section"

        await pilot.press("escape", "escape")
        await pilot.pause()


async def test_open_link_inside_the_note():
    async with run_pilot() as pilot:
        opened = []

        with patch(
            "todooit.ui.screens.note.open_url",
            lambda url: opened.append(url) or True,
        ):
            await open_note(pilot)

            await pilot.press(*list("see https://example.com here"))
            await pilot.press("escape")

            # The cursor sits at the end, past the link: no link under it
            await pilot.press("o")
            await pilot.pause()
            assert opened == []

            # Walk back onto the link and open it
            await pilot.press("b", "b")  # word left, onto the url
            await pilot.press("o")
            await pilot.pause()

            assert opened == ["https://example.com"]

        await pilot.press("escape")
        await pilot.pause()


async def test_pinned_note_via_m():
    async with run_pilot() as pilot:
        app = await boot(pilot)

        await pilot.press("m")
        await pilot.pause()

        screen = app.screen
        assert isinstance(screen, PinnedNoteScreen)
        assert screen.editor.border_title == "Pinned Note"

        await pilot.press(*list("a thought with no task yet"))
        await pilot.press("escape", "escape")
        await pilot.pause()

        assert not isinstance(app.screen, NoteScreenBase)
        assert PinnedNote.get_text() == "a thought with no task yet"

        # It is one note for the whole app: opening it again shows the same
        await pilot.press("m")
        await pilot.pause()

        screen = app.screen
        assert isinstance(screen, PinnedNoteScreen)
        assert screen.editor.text == "a thought with no task yet"

        await pilot.press("escape")
        await pilot.pause()
