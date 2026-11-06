"""
Notes: the window on a todo's note, and the pinned scratchpad
"""

from unittest.mock import patch

import pytest
from rich.cells import cell_len
from textual.geometry import Offset
from textual.widgets.text_area import Selection

from tests.test_ui.ui_base import (
    boot,
    commit_line,
    create_and_move_to_todo,
    run_pilot,
    set_clipboard,
    visible_todos,
)
from todooit.api import PinnedNote, Todo
from todooit.api.theme import TodooitThemeBase
from todooit.ui.screens.index import MainScreen
from todooit.ui.screens.note import NoteScreen, NoteScreenBase, PinnedNoteScreen
from todooit.ui.screens.note.disp.document import FoldedDocument, HangingDocument
from todooit.ui.screens.note.disp.markup import (
    EMPH,
    INDENT,
    LINK,
    MARKER,
    QUOTE,
    QUOTE_BAR,
    QUOTE_ITEM,
    draw_line,
    recount,
    scan_note,
)
from todooit.ui.screens.note.disp.theme import build_theme
from todooit.ui.screens.note.vim.modes import MODE_INSERT, MODE_NORMAL
from todooit.ui.screens.search import Found, NoteHit
from todooit.utils import Opened
from todooit.utils.default_config import NOTE_ICON
from todooit.utils.links import fold_links

# What a note writes either side of an emphasised phrase
EMPH_MARK = "**"

# The address that started all this: too long to sit on a line of its own, let
# alone inside a quote bar, and with nothing past the page name worth reading
LONG_LINK = (
    "https://atdfsds.sharepoint.com/sites/INP-TREASURY-SAL/Shared%20Documents"
    "/Forms/AllItems.aspx?d=w6b644727c5a24335bfb4a1ddf1c6e2de&csf=1&web=1"
    "&e=9pE4sh&CID=48733ba2%2Dc02d%2D3001%2D47cc%2Df67908799d9d"
)

# What it is drawn as once folded
LONG_LINK_DRAWN = "atdfsds.sharepoint.com/…/AllItems.aspx"


async def open_note(pilot, description: str = "task with a note") -> NoteScreen:
    """A project, a todo, and its note opened with space, ready to be typed in"""

    await create_and_move_to_todo(pilot)
    await pilot.press("n")
    await commit_line(pilot, description)

    await pilot.press(" ")
    await pilot.pause()

    screen = pilot.app.screen
    assert isinstance(screen, NoteScreen)

    await pilot.press("i")
    return screen


async def test_space_opens_the_note_window():
    async with run_pilot() as pilot:
        screen = await open_note(pilot, "the todo")

        assert screen.frame.border_title == "the todo"


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

        await pilot.press("i", "end")  # INSERT, where the line's end can be reached
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


async def test_normal_mode_answers_to_no_other_letter():
    """
    A letter with no command on it does nothing at all, in the text or to the
    cursor
    """

    async with run_pilot() as pilot:
        screen = await open_note(pilot)

        await pilot.press(*list("two words"))
        await pilot.press("escape")
        await pilot.pause()

        assert screen.editor.mode == MODE_NORMAL

        for key in ("q", "Q"):
            screen.editor.move_cursor((0, 0))
            await pilot.press(key)
            await pilot.pause()

            assert screen.editor.mode == MODE_NORMAL, key
            assert screen.editor.cursor_location == (0, 0), key
            assert screen.editor.text == "two words", key


async def test_the_window_takes_most_of_the_screen():
    """
    A note is read in the window, so the window is most of what is on screen
    """

    async with run_pilot() as pilot:
        screen = await open_note(pilot)
        width, height = pilot.app.size

        assert screen.frame.outer_size.width == int(width * 0.8)
        assert screen.frame.outer_size.height == int(height * 0.85)

        # The hint under it is drawn to the same width, so the two line up
        assert screen.hint.outer_size.width == screen.frame.outer_size.width

        await pilot.press("escape", "escape")
        await pilot.pause()


async def test_ctrl_u_and_ctrl_d_scroll_half_a_page():
    """
    vim's half-page keys, on a note too long to be read in one window
    """

    async with run_pilot() as pilot:
        screen = await open_note(pilot)
        editor = screen.editor

        editor.load_text("\n".join(f"line {n}" for n in range(200)))
        await pilot.press("escape")
        await pilot.pause()

        assert editor.mode == MODE_NORMAL
        assert editor.cursor_location == (0, 0)

        half = editor.half_page()
        assert half > 1

        await pilot.press("ctrl+d")
        await pilot.pause()

        # The view came with it, and the cursor keeps its 4 rows from the top
        assert editor.cursor_location == (half + 4, 0)
        assert editor.scroll_offset.y == half

        await pilot.press("ctrl+d")
        await pilot.pause()

        assert editor.cursor_location == (half * 2 + 4, 0)
        assert editor.scroll_offset.y == half * 2

        await pilot.press("ctrl+u")
        await pilot.pause()

        assert editor.cursor_location == (half + 4, 0)
        assert editor.scroll_offset.y == half

        await pilot.press("escape")
        await pilot.pause()


async def test_u_and_d_are_letters_again_in_insert():
    """The two keys are motions in NORMAL only; in INSERT they are typed"""

    async with run_pilot() as pilot:
        screen = await open_note(pilot)

        await pilot.press(*list("mud"))
        await pilot.pause()

        assert screen.editor.text == "mud"

        await pilot.press("escape", "escape")
        await pilot.pause()


async def test_clear_note_asks_first():
    async with run_pilot() as pilot:
        screen = await open_note(pilot)

        await pilot.press(*list("precious words"))
        await pilot.press("escape")

        await pilot.press("i", "ctrl+d")
        await pilot.pause()
        assert screen.awaiting_answer

        # Anything but y leaves the note exactly where it is
        await pilot.press("n")
        await pilot.pause()
        assert not screen.awaiting_answer
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


async def test_attachment_alone_marks_the_row():
    """A note that is nothing but a file still says so on the row"""

    async with run_pilot() as pilot:
        app = pilot.app
        await create_and_move_to_todo(pilot)
        await pilot.press("n")
        await commit_line(pilot, "plain")

        formatter = app.api.formatter.todos.note
        todo = Todo.all()[0]

        assert formatter.format_value(todo.note, todo).plain.strip() == ""

        todo.attachments = "/tmp/report.pdf"
        todo.save()

        assert formatter.format_value(todo.note, todo).plain.strip() != ""


def icon_drawn(pilot) -> bool:
    """Whether the note icon is on the screen in the pane in front"""

    tree = visible_todos(pilot.app)

    return any(
        NOTE_ICON in tree.render_line(y).text for y in range(tree.size.height)
    )


async def close_note(pilot) -> None:
    """Out of the window from either mode, however many presses that takes"""

    while isinstance(pilot.app.screen, NoteScreenBase):
        await pilot.press("escape")
        await pilot.pause()


async def test_writing_a_note_shows_the_icon_on_close():
    """The text isn't in the undo history, so closing has to redraw by itself"""

    async with run_pilot() as pilot:
        screen = await open_note(pilot)
        screen.editor.insert("something")
        await close_note(pilot)

        assert icon_drawn(pilot)


async def test_emptying_a_note_takes_the_icon_away_on_close():
    async with run_pilot() as pilot:
        screen = await open_note(pilot)
        screen.editor.insert("something")
        await close_note(pilot)
        assert icon_drawn(pilot)

        await pilot.press(" ")
        await pilot.pause()

        screen = pilot.app.screen
        assert isinstance(screen, NoteScreen)

        screen.editor.clear()
        await close_note(pilot)

        assert not icon_drawn(pilot)


async def test_closing_a_note_leaves_the_cursor_on_its_row():
    async with run_pilot() as pilot:
        screen = await open_note(pilot, "first")
        await close_note(pilot)

        await pilot.press("n")
        await commit_line(pilot, "second")

        tree = visible_todos(pilot.app)
        assert tree.current_model.description == "second"

        await pilot.press(" ")
        await pilot.pause()

        screen = pilot.app.screen
        assert isinstance(screen, NoteScreen)

        screen.editor.insert("something")
        await close_note(pilot)

        assert tree.current_model.description == "second"
        assert pilot.app.focused is tree


async def test_note_opened_from_the_finder_shows_the_icon_on_close():
    async with run_pilot() as pilot:
        await open_note(pilot)
        await close_note(pilot)

        main = pilot.app.screen
        assert isinstance(main, MainScreen)

        todo = Todo.all()[0]
        await main.search_done(Found(todo, NoteHit(0, 0, "")))
        await pilot.pause()

        screen = pilot.app.screen
        assert isinstance(screen, NoteScreen)

        screen.editor.insert("something")
        await close_note(pilot)

        assert icon_drawn(pilot)


async def test_emph_is_drawn_in_its_own_color():
    """
    The words between the marks are what is lit, and the spans land on the
    line as it is *drawn* - which is the line with the marks folded out of it
    """

    line = "say " + EMPH_MARK + "this" + EMPH_MARK + " twice"
    drawn, _ = fold_links(line)
    spans = list(scan_note([line]))[0]

    assert drawn == "say this twice"
    assert (EMPH, "this") in [
        (name, drawn.encode()[start:end].decode())
        for start, end, name in spans
    ]


async def test_cmd_keys_in_the_note():
    """Clear, select all and paste answer to Cmd as they do to ctrl"""

    async with run_pilot() as pilot:
        screen = await open_note(pilot)
        editor = screen.editor

        await pilot.press(*list("some words"))
        await pilot.press("escape")

        await pilot.press("super+a")
        await pilot.pause()
        assert editor.selected_text == "some words"

        set_clipboard("pasted")
        await pilot.press("super+v")
        await pilot.pause()
        assert editor.text == "pasted"

        # Pasting left it in INSERT, the mode where this clears
        await pilot.press("super+d")
        await pilot.press("y")
        await pilot.pause()
        assert editor.text == ""


async def test_the_formatting_keys_no_longer_format():
    """
    The markup is typed, not pressed: the four keys that used to write it are
    off the window, and none of them leaves a mark on the note any more
    """

    async with run_pilot() as pilot:
        screen = await open_note(pilot)

        await pilot.press(*list("plain"))
        await pilot.press("ctrl+e", "ctrl+b", "ctrl+l", "ctrl+t")
        await pilot.pause()

        assert screen.editor.text == "plain"

        await pilot.press("escape", "escape")
        await pilot.pause()


async def test_markdown_stars_still_read_as_emphasis():
    """Anything written before the mark went zero-width goes on working"""

    spans = list(scan_note(["old *style* text"]))[0]

    assert EMPH in [name for _, _, name in spans]


async def test_star_markers_are_faint_but_not_hidden():
    """
    A `*` that survives - pasted in, or written before the swap - costs its
    column either way, and one painted the color of the paper reads as an
    indent that is not there. Faint, then, but visible
    """

    theme = build_theme(TodooitThemeBase)
    marker = theme.syntax_styles[MARKER].color.triplet

    assert marker != theme.base_style.bgcolor.triplet
    assert marker != theme.syntax_styles[EMPH].color.triplet


async def test_a_quote_marker_mid_line_stays_a_greater_than_sign():
    """Only a mark at the head of a line is opening one"""

    async with run_pilot() as pilot:
        screen = await open_note(pilot)

        await pilot.press(*list("2 > 1"))
        assert screen.editor.text == "2 > 1"

        await pilot.press("escape", "escape")
        await pilot.pause()


async def test_the_cursor_never_stands_in_a_mark():
    """
    The bug: the cursor went invisible in front of an emphasised word

    A mark is worth no columns to the terminal, so a cursor drawn over one was
    a cursor drawn over nothing at all - and it stayed that way while the
    letters went in, since the mark stayed where it was. Folded off the page,
    there is no column left for it to hide in: every column the cursor can
    reach is a column with a character of the drawn line in it.
    """

    async with run_pilot() as pilot:
        screen = await open_note(pilot)

        await pilot.press(*list("say *this* twice"))
        await pilot.press("escape")

        editor = screen.editor
        drawn = editor.document[0]

        assert EMPH_MARK not in drawn

        await pilot.press("=")

        for _ in range(len(drawn)):
            _, column = editor.cursor_location

            # Standing on a character of the page, or one past the last of
            # them - and never on something drawn as nothing
            assert column <= len(drawn)
            assert column == len(drawn) or drawn[column] != EMPH_MARK

            await pilot.press("ö")

        await pilot.press("escape")
        await pilot.pause()


async def test_stars_leaning_on_a_space_stay_stars():
    """What markdown asks of a pair: `2 * 3 * 4` is arithmetic, not emphasis"""

    async with run_pilot() as pilot:
        screen = await open_note(pilot)

        await pilot.press(*list("2 * 3 * 4"))
        assert screen.editor.text == "2 * 3 * 4"
        assert list(scan_note([screen.editor.text]))[0] == []

        await pilot.press("escape", "escape")
        await pilot.pause()


async def test_enumerations_are_drawn_like_bullets():
    """A numbered list is a list: the number wears the bullet's own color"""

    lines = ["1. first", "  2. nested", "10. tenth"]
    spans = list(scan_note(lines))
    names = [[name for _, _, name in row] for row in spans]

    assert names == [["note-bullet-0"], ["note-bullet-1"], ["note-bullet-0"]]

    # And it is the number itself that is colored, not the words after it
    start, end, _ = spans[0][0]
    assert lines[0].encode()[start:end].decode() == "1. "


async def test_a_number_mid_line_is_not_an_enumeration():
    """`1.` opens a list only where a list could open: at the head of a line"""

    assert list(scan_note(["worth about 1. of a point"]))[0] == []


async def test_enter_carries_an_enumeration_on_with_the_next_number():
    """A numbered item is carried on like a bullet, one number further"""

    async with run_pilot() as pilot:
        screen = await open_note(pilot)
        editor = screen.editor

        await pilot.press(*list("1. first"))
        await pilot.press("enter")
        await pilot.press(*list("second"))
        assert editor.text == "1. first\n2. second"

        # Past nine, the number grows a digit and the cursor stays past it
        editor.text = "9. ninth"
        editor.move_cursor((0, 8))
        await pilot.press("enter")
        assert editor.text == "9. ninth\n10. "
        assert editor.cursor_location == (1, 4)

        await pilot.press("escape", "escape")
        await pilot.pause()


async def test_tab_nests_an_enumeration_and_enter_walks_it_back_out():
    """A nested list counts from one, and the one it came out of carries on"""

    async with run_pilot() as pilot:
        screen = await open_note(pilot)

        await pilot.press(*list("1. top"))
        await pilot.press("enter", "tab")
        await pilot.press(*list("a"))
        await pilot.press("enter")
        await pilot.press(*list("b"))
        assert screen.editor.text == "1. top\n  1. a\n  2. b"

        # Out of the nested list, the outer one picks up after its last number
        await pilot.press("enter", "enter")
        assert screen.editor.text == "1. top\n  1. a\n  2. b\n2. "

        # And at the top the list ends the way a bulleted one does
        await pilot.press("enter")
        assert screen.editor.text == "1. top\n  1. a\n  2. b\n"

        await pilot.press("escape", "escape")
        await pilot.pause()


async def test_an_edit_mid_list_moves_the_numbers_below_it():
    async with run_pilot() as pilot:
        screen = await open_note(pilot)
        editor = screen.editor

        editor.text = "1. a\n2. b\n3. c"
        editor.move_cursor((0, 4))
        await pilot.press("enter")
        assert editor.text == "1. a\n2. \n3. b\n4. c"

        # A tab closes the gap the item leaves behind it
        editor.move_cursor((2, 4))
        await pilot.press("tab")
        assert editor.text == "1. a\n2. \n  1. b\n3. c"

        await pilot.press("escape", "escape")
        await pilot.pause()


async def test_backspace_takes_a_nested_numbers_marker_one_character_at_a_time():
    async with run_pilot() as pilot:
        screen = await open_note(pilot)
        editor = screen.editor

        editor.text = "1. top\n  1. child"
        editor.move_cursor((1, 5))

        await pilot.press("backspace")
        assert editor.text == "1. top\n  1.child"

        await pilot.press("backspace")
        assert editor.text == "1. top\n  1child"
        assert editor.cursor_location == (1, 3)

        await pilot.press("escape", "escape")
        await pilot.pause()


async def test_an_enumeration_is_carried_on_inside_a_quote():
    async with run_pilot() as pilot:
        screen = await open_note(pilot)

        await pilot.press(*list("> "))
        await pilot.press(*list("1. said"))
        await pilot.press("enter")
        await pilot.press(*list("again"))
        assert screen.editor.text == "> 1. said\n" + "> 2. again"

        await pilot.press("escape", "escape")
        await pilot.pause()


async def test_o_opens_the_next_numbered_item():
    async with run_pilot() as pilot:
        screen = await open_note(pilot)

        await pilot.press(*list("3. third"))
        await pilot.press("escape", "o")
        await pilot.press(*list("fourth"))
        assert screen.editor.text == "3. third\n4. fourth"

        await pilot.press("escape", "escape")
        await pilot.pause()


@pytest.mark.parametrize(
    "lines, row, counted",
    [
        # Each depth counts on; a nested list starts over
        (["1. a", "1. b", "  5. x", "  5. y", "7. c"], 1, ["1. a", "2. b", "  1. x", "  2. y", "3. c"]),
        # Stepped out of a nested list: the outer one counts it in, the rest starts over
        (["1. a", "  1. x", "2. y", "  3. z", "2. b"], 2, ["1. a", "  1. x", "2. y", "  1. z", "3. b"]),
        # The first item's own number opens the count
        (["5. a", "1. b"], 1, ["5. a", "6. b"]),
        # A blank line ends the list, and so does a change of quote
        (["1. a", "", "9. b"], 0, ["1. a", "", "9. b"]),
        (["> 1. a", "1. b"], 0, ["> 1. a", "1. b"]),
        # A bullet is counted around, and restarts the count after it
        (["1. a", "- b", "4. c"], 0, ["1. a", "- b", "1. c"]),
        (["- a", "  - b"], 0, ["- a", "  - b"]),
        (["plain"], 0, ["plain"]),
    ],
)
def test_recount(lines, row, counted):
    edited = list(lines)

    for at, start, end, marker in recount(lines, row):
        edited[at] = edited[at][:start] + marker + edited[at][end:]

    assert edited == counted


async def test_a_dash_put_mid_line_stays_a_hyphen():
    """In front of existing words, but after other words: still a hyphen"""

    async with run_pilot() as pilot:
        screen = await open_note(pilot)

        await pilot.press(*list("well almost"))
        await pilot.press(*["left"] * len("almost"))
        await pilot.press(*list("- "))
        assert screen.editor.text == "well - almost"

        await pilot.press("escape", "escape")
        await pilot.pause()


async def test_a_dash_mid_line_stays_a_hyphen():
    """Only a mark at the head of a line is opening one"""

    async with run_pilot() as pilot:
        screen = await open_note(pilot)

        await pilot.press(*list("well - almost"))
        assert screen.editor.text == "well - almost"

        # And an angle bracket in the middle of a line is just as literal
        await pilot.press("enter")
        await pilot.press(*list("a > b"))
        assert screen.editor.text.splitlines()[1] == "a > b"

        await pilot.press("escape", "escape")
        await pilot.pause()


async def test_a_quoted_marker_is_green_rather_than_its_depth():
    """
    Inside a quote the color is spoken for - it says the line is quoted - so
    the glyph and the indent are left to say how deep the item sits
    """

    lines = [
        "> - an item worth quoting",
        ">   - and one under it",
        "> 1. numbered, and quoted too",
    ]
    names = [[name for _, _, name in row] for row in scan_note(lines)]

    assert names == [[QUOTE, QUOTE_BAR, QUOTE_ITEM]] * 3

    theme = build_theme(TodooitThemeBase)

    assert (
        theme.syntax_styles[QUOTE_ITEM].color.triplet
        == theme.syntax_styles[QUOTE].color.triplet
    )
    assert theme.syntax_styles[QUOTE_ITEM].bold


async def test_tab_nests_a_bullet_inside_its_quote():
    """The bar stays at the head of the line; the indent grows after it"""

    async with run_pilot() as pilot:
        screen = await open_note(pilot)

        await pilot.press(*list("> "))
        await pilot.press(*list("- top"))
        await pilot.press("enter")
        await pilot.press(*list("child"))
        await pilot.press("tab")

        assert screen.editor.text == (
            "> - top\n" + ">   - child"
        )

        # Still quoted at every level it reaches
        names = [
            [name for _, _, name in row]
            for row in scan_note(screen.editor.text.splitlines())
        ]
        assert names == [[QUOTE, QUOTE_BAR, QUOTE_ITEM]] * 2

        await pilot.press("escape", "escape")
        await pilot.pause()


async def test_an_empty_quoted_item_unwinds_one_marker_at_a_time():
    """The bullet ends the list, and the bar ends the quote after it"""

    async with run_pilot() as pilot:
        screen = await open_note(pilot)

        await pilot.press(*list("> "))
        await pilot.press(*list("- item"))

        written = "> - item\n"

        await pilot.press("enter")
        assert screen.editor.text == written + "> - "

        await pilot.press("enter")
        assert screen.editor.text == written + "> "

        await pilot.press("enter")
        assert screen.editor.text == written

        await pilot.press("escape", "escape")
        await pilot.pause()


async def test_a_quoted_line_is_green_behind_its_bar():
    line = "> a snippet worth keeping"
    names = [name for _, _, name in list(scan_note([line]))[0]]

    assert names == [QUOTE, QUOTE_BAR]


async def test_a_long_link_is_styled_where_it_is_drawn():
    """
    The underline lands on the name the link is folded to, not on the address
    that name stands in for
    """

    line = "> see " + LONG_LINK + " here"
    (spans,) = list(scan_note([line]))

    assert [name for _, _, name in spans] == [QUOTE, QUOTE_BAR, LINK]

    drawn = draw_line(line)
    start, end, _ = spans[-1]

    # The spans are counted in bytes of the drawn line, which is what
    # `render_line` measures them against
    assert drawn.encode("utf-8")[start:end].decode("utf-8") == LONG_LINK_DRAWN


async def test_a_named_link_is_styled_on_the_name_it_is_drawn_under():
    line = "see [the folder](" + LONG_LINK + ") here"
    (spans,) = list(scan_note([line]))

    start, end, name = spans[-1]
    drawn, _ = fold_links(line)

    assert name == LINK
    assert drawn.encode("utf-8")[start:end].decode("utf-8") == "the folder"


async def test_a_long_link_in_a_quote_stays_inside_the_block():
    async with run_pilot() as pilot:
        screen = await open_note(pilot)
        editor = screen.editor

        editor.load_text("a line\n" + "> see " + LONG_LINK + " here")
        await pilot.pause()

        assert editor.document.get_line(1) == (
            "▎ see " + LONG_LINK_DRAWN + " here"
        )

        # One row on the page: nothing has wrapped out from under the bar,
        # which is what used to take the link out of the block
        assert editor.wrapped_document.get_offsets(1) == []

        # And nothing was taken out of the note to get there
        assert LONG_LINK in editor.text

        await pilot.press("escape", "escape")
        await pilot.pause()


async def test_the_cursor_line_shows_a_link_in_full():
    """
    Standing on a line shows what is written on it, columns and all; every
    other line goes on showing the name
    """

    written = "see [the folder](" + LONG_LINK + ") here"

    async with run_pilot() as pilot:
        screen = await open_note(pilot)
        editor = screen.editor

        editor.load_text("a line\n" + written)
        await pilot.pause()

        assert editor.document.get_line(1) == "see the folder here"

        editor.move_cursor((1, 0))
        await pilot.pause()

        assert editor.document.get_line(1) == written

        # A cursor column on this line is a column of the stored text
        editor.move_cursor((1, written.index("https")))
        await pilot.pause()

        assert editor.cursor_location == (1, written.index("https"))
        assert editor.document[1][editor.cursor_location[1]] == "h"

        # Leaving folds it back, and nothing was lost behind the name
        editor.move_cursor((0, 0))
        await pilot.pause()

        assert editor.document.get_line(1) == "see the folder here"
        assert editor.text == "a line\n" + written

        await pilot.press("escape", "escape")
        await pilot.pause()


async def test_a_name_is_edited_on_the_stored_text():
    """
    The cursor line is the stored text, so a name is retyped like any other
    words and the folded line picks the new name up
    """

    async with run_pilot() as pilot:
        screen = await open_note(pilot)
        editor = screen.editor

        editor.load_text("see [the folder](" + LONG_LINK + ") here\nbelow")
        await pilot.pause()

        # Between "the " and "folder"
        editor.move_cursor((0, 9))
        await pilot.press(*list("big "))
        await pilot.pause()

        assert editor.text == "see [the big folder](" + LONG_LINK + ") here\nbelow"

        editor.move_cursor((1, 0))
        await pilot.pause()

        assert editor.document.get_line(0) == "see the big folder here"

        await pilot.press("escape", "escape")
        await pilot.pause()


async def test_indenting_a_line_keeps_the_address_on_it():
    """
    The one rewrite that puts a whole line back has to put back the line that
    was really there, not the one that was drawn
    """

    async with run_pilot() as pilot:
        screen = await open_note(pilot)
        editor = screen.editor

        editor.load_text("see [the folder](" + LONG_LINK + ") here")
        await pilot.pause()

        await pilot.press("tab")
        await pilot.pause()

        assert editor.text == "  see [the folder](" + LONG_LINK + ") here"

        await pilot.press("escape", "escape")
        await pilot.pause()


async def test_backspace_on_the_cursor_line_takes_one_stored_character():
    """Nothing is folded under the cursor, so nothing widens an edit into a link"""

    async with run_pilot() as pilot:
        screen = await open_note(pilot)
        editor = screen.editor

        editor.load_text("see [](" + LONG_LINK + ")")
        await pilot.pause()

        editor.move_cursor(editor.document.end)
        await pilot.press("backspace")
        await pilot.pause()

        assert editor.text == "see [](" + LONG_LINK

        await pilot.press("escape", "escape")
        await pilot.pause()


async def test_a_line_rewraps_with_its_hanging_indent_as_the_cursor_passes():
    async with run_pilot() as pilot:
        screen = await open_note(pilot)
        editor = screen.editor

        editor.load_text("a line\n- see [the folder](" + LONG_LINK + ") here")
        await pilot.pause()

        wrapped = editor.wrapped_document
        assert isinstance(wrapped, HangingDocument)
        assert wrapped.get_offsets(1) == []

        editor.move_cursor((1, 0))
        await pilot.pause()

        # Wrapped, and every row past the first sits under the bullet's words
        assert wrapped.get_offsets(1) != []
        assert wrapped.hanging_pad(1, 1) == 2

        editor.move_cursor((0, 0))
        await pilot.pause()

        assert wrapped.get_offsets(1) == []
        assert wrapped.height == 2

        await pilot.press("escape", "escape")
        await pilot.pause()


async def test_a_line_above_the_view_changing_height_does_not_move_the_view():
    filler = "\n".join(f"line {number}" for number in range(80))

    async with run_pilot() as pilot:
        screen = await open_note(pilot)
        editor = screen.editor

        editor.load_text("see [the folder](" + LONG_LINK + ") here\n" + filler)
        await pilot.pause()

        wrapped = editor.wrapped_document
        assert isinstance(wrapped, HangingDocument)
        assert wrapped.get_offsets(0) != []

        editor.scroll_to(y=20, animate=False, immediate=True)
        await pilot.pause()

        top_line = wrapped.row_at(editor.scroll_offset.y)
        # Well inside the view: a click nearer its edge scrolls, to keep context
        clicked = wrapped.row_at(editor.scroll_offset.y + 6)
        assert clicked is not None

        # The raw line above the view folds up when the click takes the cursor away
        await pilot.click(editor, offset=(editor.gutter.left, editor.gutter.top + 6))
        await pilot.pause()

        assert editor.cursor_location[0] == clicked[0]
        assert wrapped.get_offsets(0) == []
        assert wrapped.row_at(editor.scroll_offset.y) == top_line

        await pilot.press("escape", "escape")
        await pilot.pause()


async def test_moving_by_screen_row_crosses_raw_and_folded_lines():
    written = "see [the folder](" + LONG_LINK + ") here"

    async with run_pilot() as pilot:
        screen = await open_note(pilot)
        editor = screen.editor

        editor.load_text("a plain line up here\n" + written + "\nanother plain line")
        await pilot.pause()

        # Over the second "e" of "the" as the line is drawn folded
        editor.move_cursor((0, 6))
        editor.action_cursor_down()
        await pilot.pause()

        row, column = editor.cursor_location
        assert (row, column) == (1, written.index("the") + 2)

        # Down through the rows the raw line wraps to, and on past it
        rows = len(editor.wrapped_document.get_offsets(1)) + 1

        for _ in range(rows):
            editor.action_cursor_down()
            await pilot.pause()

        assert editor.cursor_location[0] == 2
        assert editor.document.get_line(1) == "see the folder here"

        # And back up: on to the line and off it the other side, never stuck
        visited = set()

        for _ in range(rows + 2):
            editor.action_cursor_up()
            await pilot.pause()
            visited.add(editor.cursor_location[0])

        assert visited == {0, 1}
        assert editor.cursor_location[0] == 0

        await pilot.press("escape", "escape")
        await pilot.pause()


async def test_a_click_on_a_folded_line_lands_on_the_character_clicked():
    written = "see [the folder](" + LONG_LINK + ") here"

    async with run_pilot() as pilot:
        screen = await open_note(pilot)
        editor = screen.editor

        editor.load_text("a line\n" + written)
        await pilot.pause()

        # The "f" of "folder", drawn at column 8 of "see the folder here"
        await pilot.click(editor, offset=(editor.gutter.left + 8, editor.gutter.top + 1))
        await pilot.pause()

        row, column = editor.cursor_location
        assert (row, column) == (1, written.index("folder"))

        await pilot.press("escape", "escape")
        await pilot.pause()


async def test_undoing_an_edit_made_on_a_line_the_cursor_has_left():
    """An edit's columns were raw ones; by the time of the undo that row is folded"""

    written = "see [the folder](" + LONG_LINK + ") here"

    async with run_pilot() as pilot:
        screen = await open_note(pilot)
        editor = screen.editor

        editor.load_text(written + "\nbelow")
        await pilot.pause()

        editor.move_cursor((0, len(written)))
        await pilot.press("!")
        await pilot.pause()

        editor.move_cursor((1, 0))
        await pilot.pause()

        editor.action_undo()
        await pilot.pause()

        assert editor.text == written + "\nbelow"
        assert editor.cursor_location == (0, len(written))
        assert editor.document.get_line(0) == written

        editor.action_redo()
        await pilot.pause()

        assert editor.text == written + "!\nbelow"

        await pilot.press("escape", "escape")
        await pilot.pause()


async def test_go_to_lands_inside_a_links_address():
    written = "see [the folder](" + LONG_LINK + ") here"

    async with run_pilot() as pilot:
        screen = await open_note(pilot)
        editor = screen.editor

        editor.load_text("a line\n" + written)
        await pilot.pause()

        column = written.index("AllItems")
        screen.go_to(1, column)
        await pilot.pause()

        assert editor.cursor_location == (1, column)

        await pilot.press("escape", "escape")
        await pilot.pause()


async def test_joining_up_to_a_folded_line_keeps_its_link_whole():
    async with run_pilot() as pilot:
        screen = await open_note(pilot)
        editor = screen.editor

        editor.load_text("see [n](" + LONG_LINK + ")\nnext")
        await pilot.pause()

        editor.move_cursor((1, 0))
        await pilot.press("backspace")
        await pilot.pause()

        assert editor.text == "see [n](" + LONG_LINK + ")next"

        await pilot.press("escape", "escape")
        await pilot.pause()


async def test_joining_a_folded_line_up_keeps_its_link_whole():
    async with run_pilot() as pilot:
        screen = await open_note(pilot)
        editor = screen.editor

        editor.load_text("abc\n[n](" + LONG_LINK + ") tail")
        await pilot.pause()

        editor.move_cursor((0, 3))
        await pilot.press("delete")
        await pilot.pause()

        assert editor.text == "abc[n](" + LONG_LINK + ") tail"

        await pilot.press("escape", "escape")
        await pilot.pause()


async def test_enter_before_a_link_lands_at_the_line_start_and_undoes_cleanly():
    written = "abc [n](" + LONG_LINK + ") tail"

    async with run_pilot() as pilot:
        screen = await open_note(pilot)
        editor = screen.editor

        editor.load_text(written)
        await pilot.pause()

        editor.move_cursor((0, 4))
        await pilot.press("enter")
        await pilot.pause()

        assert editor.cursor_location == (1, 0)

        editor.action_undo()
        await pilot.pause()

        assert editor.text == written

        await pilot.press("escape", "escape")
        await pilot.pause()


async def test_the_start_of_a_folded_line_is_the_start_of_the_raw_one():
    async with run_pilot() as pilot:
        screen = await open_note(pilot)
        editor = screen.editor

        editor.load_text("[n](" + LONG_LINK + ") tail\nbelow")
        await pilot.pause()

        editor.move_cursor((1, 0))
        await pilot.pause()

        editor.action_note_start()
        await pilot.pause()

        assert editor.cursor_location == (0, 0)

        await pilot.press("escape", "escape")
        await pilot.pause()


async def test_renumbering_another_row_leaves_the_cursor_on_its_words():
    written = "1. see [n](" + LONG_LINK + ") tail"

    async with run_pilot() as pilot:
        screen = await open_note(pilot)
        editor = screen.editor

        editor.load_text(written + "\n5. b")
        await pilot.pause()

        column = written.index("tail")
        editor.move_cursor((0, column))
        await pilot.press("tab")
        await pilot.pause()

        row, landed = editor.cursor_location
        assert row == 0
        assert editor.document[0][landed:] == "tail"
        assert editor.text.split("\n")[1] == "1. b"

        await pilot.press("escape", "escape")
        await pilot.pause()


async def test_pasting_lines_ending_in_a_link_leaves_the_cursor_past_it():
    last = "second [n](" + LONG_LINK + ")"

    async with run_pilot() as pilot:
        screen = await open_note(pilot)
        editor = screen.editor

        set_clipboard("first\n" + last)
        await pilot.press("ctrl+v")
        await pilot.pause()

        assert editor.cursor_location == (1, len(last))

        await pilot.press("escape", "escape")
        await pilot.pause()


async def test_a_click_on_a_short_bare_address_lands_on_the_character_clicked():
    written = "see https://example.com/x here"

    async with run_pilot() as pilot:
        screen = await open_note(pilot)
        editor = screen.editor

        editor.load_text("a line\n" + written)
        await pilot.pause()

        column = written.index("example")
        await pilot.click(
            editor, offset=(editor.gutter.left + column, editor.gutter.top + 1)
        )
        await pilot.pause()

        assert editor.cursor_location == (1, column)

        await pilot.press("escape", "escape")
        await pilot.pause()


async def test_a_click_on_a_name_opening_the_line_lands_on_its_first_letter():
    async with run_pilot() as pilot:
        screen = await open_note(pilot)
        editor = screen.editor

        editor.load_text("a line\n[name](" + LONG_LINK + ") tail")
        await pilot.pause()

        await pilot.click(editor, offset=(editor.gutter.left, editor.gutter.top + 1))
        await pilot.pause()

        assert editor.cursor_location == (1, 1)

        await pilot.press("escape", "escape")
        await pilot.pause()


async def test_copying_a_link_carries_its_address():
    """
    What is picked out on the page comes back as what is written behind it
    """

    async with run_pilot() as pilot:
        screen = await open_note(pilot)
        editor = screen.editor

        editor.load_text("see [the folder](" + LONG_LINK + ") here")
        await pilot.pause()

        await pilot.press("ctrl+a")
        await pilot.pause()

        assert editor.selected_text == "see [the folder](" + LONG_LINK + ") here"

        await pilot.press("escape", "escape")
        await pilot.pause()


async def test_gx_opens_a_folded_link_in_full():
    async with run_pilot() as pilot:
        opened = []

        with patch(
            "todooit.ui.screens.note.screens.screen.open_url",
            lambda url: opened.append(url) or True,
        ):
            screen = await open_note(pilot)
            editor = screen.editor

            editor.load_text("see [the folder](" + LONG_LINK + ") here")
            await pilot.pause()

            await pilot.press("escape")

            # Anywhere on the name it is drawn under
            editor.move_cursor((0, 6))
            await pilot.press("g", "x")
            await pilot.pause()

            assert opened == [LONG_LINK]

        await pilot.press("escape")
        await pilot.pause()


async def test_pasting_a_long_link_leaves_it_unnamed():
    """
    An unnamed link is drawn as a shortened form of its own address, which is
    the most useful thing it can say before anyone has named it
    """

    async with run_pilot() as pilot:
        screen = await open_note(pilot)
        editor = screen.editor

        set_clipboard(LONG_LINK)
        await pilot.press("ctrl+v")
        await pilot.pause()

        written = "[](" + LONG_LINK + ")"

        assert editor.text == written

        # Past the whole of it, where there is more of the note to write
        assert editor.cursor_location == (0, len(written))

        await pilot.press("enter")
        await pilot.pause()

        assert editor.document.get_line(0) == LONG_LINK_DRAWN

        await pilot.press("escape", "escape")
        await pilot.pause()


async def test_pasting_a_long_link_over_a_phrase_names_it_after_the_phrase():
    async with run_pilot() as pilot:
        screen = await open_note(pilot)
        editor = screen.editor

        editor.load_text("the folder")
        await pilot.pause()

        await pilot.press("ctrl+a")
        set_clipboard(LONG_LINK)
        await pilot.press("ctrl+v")
        await pilot.pause()

        assert editor.text == "[the folder](" + LONG_LINK + ")"

        await pilot.press("escape", "escape")
        await pilot.pause()


async def test_a_short_link_is_pasted_in_as_it_stands():
    """Wrapping one would cost a name to write and save no room at all"""

    async with run_pilot() as pilot:
        screen = await open_note(pilot)
        editor = screen.editor

        set_clipboard("https://example.com")
        await pilot.press("ctrl+v")
        await pilot.pause()

        assert editor.text == "https://example.com"

        await pilot.press("escape", "escape")
        await pilot.pause()


async def test_a_quote_still_holds_markup():
    """A quoted line is still a line of the note: links and emphasis work"""

    emphasised = EMPH_MARK + "this" + EMPH_MARK
    line = "> see " + emphasised + " at https://example.com"
    names = [name for _, _, name in list(scan_note([line]))[0]]

    assert names[:2] == [QUOTE, QUOTE_BAR]
    assert EMPH in names


async def test_tab_nests_a_bullet():
    async with run_pilot() as pilot:
        screen = await open_note(pilot)

        await pilot.press(*list("- top"))

        # Enter carries the bullet on, tab takes the new one a level in - and
        # the glyph changes with it, so the depth is readable without counting
        await pilot.press("enter")
        await pilot.press(*list("child"))
        await pilot.press("tab")
        assert screen.editor.text == "- top\n  - child"

        # A second level in, and the glyph changes again
        await pilot.press("tab")
        assert screen.editor.text == "- top\n    - child"

        # And back out the way it came
        await pilot.press("shift+tab", "shift+tab")
        assert screen.editor.text == "- top\n- child"

        await pilot.press("escape", "escape")
        await pilot.pause()

        assert Todo.all()[0].note == "- top\n- child"


async def test_enter_on_an_empty_nested_bullet_steps_out_a_level():
    """
    The bug: `enter` on an empty nested item threw the marker away

    Which is the right end for a list at its top level and the wrong one for a
    branch of it: the way back up from a nested bullet was to press the key
    and then type the marker again by hand. It walks out a level at a time
    now, and the marker still goes on the `enter` pressed at the top, where
    there is nothing left to climb to.
    """

    async with run_pilot() as pilot:
        screen = await open_note(pilot)

        await pilot.press(*list("- top"))
        await pilot.press("enter", "tab")
        await pilot.press(*list("child"))
        await pilot.press("enter", "tab")
        await pilot.press(*list("grandchild"))

        written = "- top\n  - child\n    - grandchild\n"

        # Out of the deepest level, and the glyph comes back with it
        await pilot.press("enter", "enter")
        assert screen.editor.text == written + "  - "

        await pilot.press("enter")
        assert screen.editor.text == written + "- "

        # And at the top the list ends the way it always did
        await pilot.press("enter")
        assert screen.editor.text == written

        await pilot.press("escape", "escape")
        await pilot.pause()


async def test_an_empty_nested_bullet_steps_out_inside_a_quote_too():
    """A list written in a quote nests inside the bar, and unwinds inside it"""

    async with run_pilot() as pilot:
        screen = await open_note(pilot)

        await pilot.press(*list("> "))
        await pilot.press(*list("- item"))
        await pilot.press("enter", "tab")
        await pilot.press(*list("under"))

        written = "> - item\n" + ">   - under\n"

        await pilot.press("enter", "enter")
        assert screen.editor.text == written + "> - "

        # The bar is the last thing to go, as it always was
        await pilot.press("enter")
        assert screen.editor.text == written + "> "

        await pilot.press("escape", "escape")
        await pilot.pause()


async def test_backspace_takes_a_nested_bullets_marker_and_indent_like_any_text():
    async with run_pilot() as pilot:
        screen = await open_note(pilot)
        editor = screen.editor

        await pilot.press(*list("- top"))
        await pilot.press("enter", "tab")
        await pilot.press(*list("child"))
        await pilot.press("enter", "tab")
        await pilot.press(*list("grandchild"))

        # Back to the head of the words, where the marker ends
        editor.move_cursor((2, 6))

        await pilot.press("backspace")
        assert editor.text == "- top\n  - child\n    -grandchild"

        await pilot.press("backspace")
        assert editor.text == "- top\n  - child\n    grandchild"

        # The indent goes a space at a time, not a level at a time
        await pilot.press("backspace")
        assert editor.text == "- top\n  - child\n   grandchild"

        await pilot.press("backspace", "backspace", "backspace")
        assert editor.text == "- top\n  - child\ngrandchild"

        # And from the margin it joins the line above
        await pilot.press("backspace")
        assert editor.text == "- top\n  - childgrandchild"

        await pilot.press("escape", "escape")
        await pilot.pause()


async def test_backspace_takes_a_quoted_bullets_marker_like_any_text():
    async with run_pilot() as pilot:
        screen = await open_note(pilot)
        editor = screen.editor

        await pilot.press(*list("> "))
        await pilot.press(*list("- item"))
        await pilot.press("enter", "tab")

        written = "> - item\n"
        assert editor.text == written + ">   - "

        await pilot.press("backspace")
        assert editor.text == written + ">   -"

        await pilot.press("backspace", "backspace", "backspace")
        assert editor.text == written + "> "

        # The bar is two characters like any other two
        await pilot.press("backspace")
        assert editor.text == written + ">"

        await pilot.press("backspace")
        assert editor.text == written

        await pilot.press("escape", "escape")
        await pilot.pause()


async def test_enter_at_a_headings_end_stops_on_the_next_line():
    """A `---` below is a line of its own, not part of the title to skip past"""

    async with run_pilot() as pilot:
        screen = await open_note(pilot)
        editor = screen.editor

        editor.text = "# Title\n---\nbody"
        editor.move_cursor((0, 7))
        await pilot.press("enter")

        assert editor.text == "# Title\n\n---\nbody"
        assert editor.cursor_location == (1, 0)

        await pilot.press("escape", "escape")
        await pilot.pause()


async def test_a_backspace_that_joins_two_lists_renumbers_them():
    async with run_pilot() as pilot:
        screen = await open_note(pilot)
        editor = screen.editor

        editor.text = "1. a\n2. b\n\n1. c\n2. d"
        editor.move_cursor((2, 0))
        await pilot.press("backspace")

        assert editor.text == "1. a\n2. b\n3. c\n4. d"

        await pilot.press("escape", "escape")
        await pilot.pause()


async def test_taking_an_items_marker_away_leaves_the_rest_of_the_list_counted():
    """What's left below is a list of its own, and its first item keeps its number"""

    async with run_pilot() as pilot:
        screen = await open_note(pilot)
        editor = screen.editor

        editor.text = "1. a\n2. b\n3. c\n4. d"
        editor.move_cursor((1, 0))
        await pilot.press("delete")

        assert editor.text == "1. a\n. b\n3. c\n4. d"

        await pilot.press("escape", "escape")
        await pilot.pause()


async def test_deleting_a_line_out_of_a_list_closes_the_gap():
    async with run_pilot() as pilot:
        screen = await open_note(pilot)
        editor = screen.editor

        editor.text = "1. a\n2. b\n3. c"
        editor.selection = Selection((0, 4), (1, 4))
        await pilot.press("backspace")

        assert editor.text == "1. a\n2. c"

        await pilot.press("escape", "escape")
        await pilot.pause()


async def test_typing_a_new_item_into_a_list_takes_its_place_in_the_count():
    async with run_pilot() as pilot:
        screen = await open_note(pilot)
        editor = screen.editor

        editor.text = "1. a\n\n2. b\n3. c"
        editor.move_cursor((1, 0))
        await pilot.press(*list("9. new"))

        assert editor.text == "1. a\n2. new\n3. b\n4. c"
        assert editor.cursor_location == (1, 6)

        await pilot.press("escape", "escape")
        await pilot.pause()


async def test_changing_a_lists_first_number_counts_on_from_it():
    async with run_pilot() as pilot:
        screen = await open_note(pilot)
        editor = screen.editor

        editor.text = "1. a\n2. b"
        editor.move_cursor((0, 0))
        await pilot.press("delete", "5")

        assert editor.text == "5. a\n6. b"

        await pilot.press("escape", "escape")
        await pilot.pause()


async def test_enter_in_front_of_a_bullet_opens_a_line_above():
    """
    The bug: `enter` from the head of a bullet wrote the marker out twice

    The prefix is carried onto the new line, so from column 0 the line below
    ended up as `- - item` - the marker it already had, behind a fresh one.
    From anywhere in front of the words the line moves down whole instead,
    with a blank one opening above it.
    """

    async with run_pilot() as pilot:
        screen = await open_note(pilot)
        editor = screen.editor

        await pilot.press(*list("- one"))
        await pilot.press("enter")
        await pilot.press(*list("two"))
        assert editor.text == "- one\n- two"

        # At the very start of the second bullet
        editor.move_cursor((1, 0))
        await pilot.press("enter")

        assert editor.text == "- one\n\n- two"
        assert editor.cursor_location == (2, 0)

        await pilot.press("escape", "escape")
        await pilot.pause()


async def test_enter_between_glyph_and_words_keeps_the_marker_whole():
    """Inside the marker counts as in front of it: the glyph is not cut up"""

    async with run_pilot() as pilot:
        screen = await open_note(pilot)
        editor = screen.editor

        await pilot.press(*list("- top"))
        await pilot.press("enter")
        await pilot.press(*list("child"))
        await pilot.press("tab")
        assert editor.text == "- top\n  - child"

        # In the indent of the nested line, short of its glyph
        editor.move_cursor((1, 1))
        await pilot.press("enter")

        assert editor.text == "- top\n\n  - child"
        assert editor.cursor_location == (2, 1)

        # And between the glyph and the space that follows it
        editor.move_cursor((2, 3))
        await pilot.press("enter")

        assert editor.text == "- top\n\n\n  - child"
        assert editor.cursor_location == (3, 3)

        await pilot.press("escape", "escape")
        await pilot.pause()


async def test_enter_at_the_words_still_opens_an_empty_bullet_above():
    """Past the marker is where `enter` goes back to carrying one on"""

    async with run_pilot() as pilot:
        screen = await open_note(pilot)
        editor = screen.editor

        await pilot.press(*list("- item"))

        editor.move_cursor((0, 2))
        await pilot.press("enter")

        assert editor.text == "- \n- item"

        await pilot.press("escape", "escape")
        await pilot.pause()


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


async def test_tab_nests_a_quoted_line_after_its_bar():
    async with run_pilot() as pilot:
        screen = await open_note(pilot)
        editor = screen.editor

        editor.text = "> said\n> - item"
        editor.move_cursor((0, 6))
        await pilot.press("tab")
        assert editor.text == ">   said\n> - item"
        assert editor.cursor_location == (0, 8)

        await pilot.press("shift+tab", "shift+tab")
        assert editor.text == "> said\n> - item"

        editor.move_cursor((1, 4))
        await pilot.press("tab")
        assert editor.text == "> said\n>   - item"

        await pilot.press("shift+tab")
        assert editor.text == "> said\n> - item"

        await pilot.press("escape", "escape")
        await pilot.pause()


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


async def test_a_hash_mid_line_stays_a_number_sign():
    """Only a mark at the head of a line is opening one"""

    async with run_pilot() as pilot:
        screen = await open_note(pilot)

        await pilot.press(*list("issue #4 again"))
        assert screen.editor.text == "issue #4 again"

        await pilot.press("escape", "escape")
        await pilot.pause()


async def test_open_link_inside_the_note():
    async with run_pilot() as pilot:
        opened = []

        with patch(
            "todooit.ui.screens.note.screens.screen.open_url",
            lambda url: opened.append(url) or True,
        ):
            await open_note(pilot)

            await pilot.press(*list("see https://example.com here"))
            await pilot.press("escape")

            # The cursor sits at the end, past the link: no link under it
            await pilot.press("g", "x")
            await pilot.pause()
            assert opened == []

            # Walk back onto the link and open it: `see ` is four columns, so
            # the fifth is the first of the folded address
            await pilot.press("=", "ö", "ö", "ö", "ö")
            await pilot.press("g", "x")
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
        assert screen.frame.border_title == "Pinned Note"

        await pilot.press("i", *list("a thought with no task yet"))
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


# --- a line too long for the window ---------------------------------------

# Long enough to wrap two or three times over in any window a note is opened
# in, so that what is asked below is asked of a continuation and not only of a
# line that happened to run one word past the edge
LONG_TEXT = (
    "alpha beta gamma delta epsilon zeta eta theta iota kappa lambda mu nu "
    "xi omicron pi rho sigma tau upsilon phi chi psi omega"
)


def wrapped(line: str, width: int = 40) -> HangingDocument:
    """One line of a note, wrapped into a window `width` columns wide"""

    return HangingDocument(FoldedDocument(line), width=width, tab_width=len(INDENT))


def rows(document: HangingDocument) -> list:
    """
    Every row the one line of `document` is drawn across, each with the indent
    it is drawn behind written out in front of it
    """

    return [
        " " * document.hanging_pad(0, index) + section
        for index, section in enumerate(document.get_sections(0))
    ]


async def test_a_wrapped_bullet_keeps_its_indent():
    """
    The bug this is all here for: an item long enough to wrap used to have its
    second row drawn from the margin, which reads as a line out of the list
    """

    drawn = rows(wrapped("- " + LONG_TEXT))

    assert len(drawn) > 1
    assert all(row.startswith(INDENT) and row[2] != " " for row in drawn[1:])


async def test_a_nested_bullet_wraps_under_its_own_words():
    line = INDENT * 2 + "- " + LONG_TEXT
    drawn = rows(wrapped(line))

    # Six columns: two levels of indent and the glyph with its space, which is
    # exactly where the words of the first row start
    assert len(drawn) > 1
    assert all(row.startswith(" " * 6) and row[6] != " " for row in drawn[1:])


async def test_a_wrapped_enumeration_keeps_its_indent():
    drawn = rows(wrapped("1. " + LONG_TEXT))

    assert len(drawn) > 1
    assert all(row.startswith(" " * 3) and row[3] != " " for row in drawn[1:])


async def test_a_wrapped_quoted_bullet_stays_inside_its_block():
    drawn = rows(wrapped("> - " + LONG_TEXT))

    assert len(drawn) > 1
    assert all(row.startswith(" " * 4) and row[4] != " " for row in drawn[1:])


async def test_a_wrapped_quote_keeps_its_bar_on_every_row():
    document = wrapped("> " + LONG_TEXT)

    assert document.get_offsets(0)
    assert document.bar_at(0) is None
    assert all(document.bar_at(row) == 0 for row in range(1, document.height))


async def test_a_wrapped_line_outside_a_quote_draws_no_bar():
    document = wrapped("- " + LONG_TEXT)

    assert document.get_offsets(0)
    assert all(document.bar_at(row) is None for row in range(document.height))


async def test_an_indented_line_with_no_marker_keeps_its_indent_too():
    drawn = rows(wrapped(INDENT + LONG_TEXT))

    assert len(drawn) > 1
    assert all(row.startswith(INDENT) and row[2] != " " for row in drawn[1:])


async def test_a_line_at_the_margin_still_wraps_to_the_margin():
    drawn = rows(wrapped(LONG_TEXT))

    assert len(drawn) > 1
    assert not any(row.startswith(" ") for row in drawn)


async def test_an_indented_row_still_fits_the_window():
    """
    The indent is taken out of the width the line is wrapped at, rather than
    added to a row already as wide as the window
    """

    for line in ("- " + LONG_TEXT, INDENT * 2 + "- " + LONG_TEXT, "1. " + LONG_TEXT):
        assert all(cell_len(row) <= 40 for row in rows(wrapped(line)))


async def test_a_deep_item_in_a_narrow_window_gives_the_indent_up():
    """
    Past some depth there is more indent than window, and a column of text a
    few characters wide is worse than a row that starts at the margin
    """

    document = wrapped(INDENT * 6 + "- " + LONG_TEXT, width=20)

    assert document.get_offsets(0)
    assert document.hanging_pad(0, 1) == 0


async def test_a_column_of_a_wrapped_row_is_read_where_it_is_drawn():
    """
    What the cursor and the mouse are both mapped through: a column three in
    from the words of the second row, which is five in from the window's edge
    """

    document = wrapped("- " + LONG_TEXT)
    (break_at, *_) = document.get_offsets(0)

    assert document.location_to_offset((0, break_at + 3)) == (5, 1)
    assert document.offset_to_location(Offset(5, 1)) == (0, break_at + 3)


async def test_a_wrapped_bullet_is_drawn_under_its_words():
    async with run_pilot() as pilot:
        screen = await open_note(pilot)
        editor = screen.editor

        editor.load_text(INDENT * 2 + "- " + LONG_TEXT)
        await pilot.pause()

        assert editor.wrapped_document.get_offsets(0)

        first, second = editor.render_line(0).text, editor.render_line(1).text

        assert second.startswith(" " * 6)
        assert second.strip()

        # The row is padded, not shifted: nothing was pushed off the end of it
        assert cell_len(second) == cell_len(first)
        assert (
            second.split()
            == rows(wrapped(editor.document[0], editor.wrap_width))[1].split()
        )

        await pilot.press("escape", "escape")
        await pilot.pause()


async def test_the_cursor_keeps_its_column_into_a_wrapped_row():
    async with run_pilot() as pilot:
        screen = await open_note(pilot)
        editor = screen.editor

        editor.load_text(INDENT * 2 + "- " + LONG_TEXT)
        await pilot.pause()

        editor.move_cursor((0, 20))
        wrapped_document = editor.wrapped_document

        assert wrapped_document.location_to_offset(editor.cursor_location) == (20, 0)

        editor.action_cursor_down()
        await pilot.pause()

        # Down a row and nowhere else: the cursor is drawn in the column it
        # was in, although the row under it starts six columns along
        assert wrapped_document.location_to_offset(editor.cursor_location) == (20, 1)
        assert editor.cursor_location[1] > 20

        editor.action_cursor_up()
        await pilot.pause()

        assert editor.cursor_location == (0, 20)

        await pilot.press("escape", "escape")
        await pilot.pause()


# --- the files a note carries ---------------------------------------------


async def attach(pilot, screen, *paths):
    """Put `paths` on the clipboard and paste them into the open note"""

    set_clipboard("\n".join(str(path) for path in paths))

    await pilot.press("ctrl+v")
    await pilot.pause()

    return screen.files.paths


def drawn(screen) -> str:
    """The strip as the window paints it"""

    return screen.files.render().plain


async def test_a_pasted_path_is_attached_beside_the_note(tmp_path):
    async with run_pilot() as pilot:
        screen = await open_note(pilot)
        report = tmp_path / "Q3 report.pdf"
        report.write_text("x")

        await pilot.press(*list("some words"))
        await pilot.press("escape")

        assert not screen.files.display

        paths = await attach(pilot, screen, report)

        # Beside the note, not in it: what was written stays exactly as it was
        assert screen.editor.text == "some words"
        assert paths == [report]
        assert screen.files.display
        assert "Q3 report.pdf" in drawn(screen)

        # And it is the todo that carries it, one path per line
        assert screen.todo.attachments == str(report)

        # Attaching is not typing: the note is not edited and the cursor is
        # left standing exactly where it was
        assert screen.editor.mode == MODE_NORMAL
        assert screen.editor.cursor_location == (0, len("some words") - 1)


async def test_what_is_attached_comes_back_with_the_note(tmp_path):
    async with run_pilot() as pilot:
        screen = await open_note(pilot)
        await pilot.press("escape")
        await attach(pilot, screen, tmp_path / "one.md")

        await pilot.press("escape")
        await pilot.pause()

        # Open it again: the strip is drawn from the database, not remembered
        await pilot.press(" ")
        await pilot.pause()

        assert pilot.app.screen.files.paths == [tmp_path / "one.md"]


async def test_the_same_file_twice_is_refused(tmp_path):
    async with run_pilot() as pilot:
        screen = await open_note(pilot)

        await pilot.press("escape")
        await attach(pilot, screen, tmp_path / "one.md")
        paths = await attach(pilot, screen, tmp_path / "one.md")

        assert paths == [tmp_path / "one.md"]
        assert "Already attached" in str(screen.hint.render())


async def test_several_files_at_once(tmp_path):
    async with run_pilot() as pilot:
        screen = await open_note(pilot)

        await pilot.press("escape")
        paths = await attach(pilot, screen, tmp_path / "a.md", tmp_path / "b.pdf")

        assert paths == [tmp_path / "a.md", tmp_path / "b.pdf"]
        assert "Attached 2 files" in str(screen.hint.render())


async def test_a_copied_file_leaves_no_text_to_paste(tmp_path):
    """The clipboard holds the file itself, so the desktop is asked for it"""

    async with run_pilot() as pilot:
        screen = await open_note(pilot)
        report = tmp_path / "copied.pdf"

        await pilot.press("escape")
        set_clipboard("")

        with patch("todooit.ui.screens.note.vim.clipboard.paste_files", lambda: [str(report)]):
            await pilot.press("ctrl+v")
            await pilot.pause()

        assert screen.files.paths == [report]


async def test_a_pasted_sentence_is_still_a_sentence(tmp_path):
    async with run_pilot() as pilot:
        screen = await open_note(pilot)

        await pilot.press("escape")
        set_clipboard("the file is in /mnt/c/data/notes.md")

        await pilot.press("ctrl+v")
        await pilot.pause()

        assert screen.files.paths == []
        assert "the file is in" in screen.editor.text


async def test_gf_picks_the_files_up_and_escape_puts_them_down(tmp_path):
    async with run_pilot() as pilot:
        screen = await open_note(pilot)

        await pilot.press(*list("some words"))
        await pilot.press("escape")

        # Nothing attached: the key says so and the text keeps the keyboard
        await pilot.press("g", "f")
        await pilot.pause()
        assert not screen.picking_files
        assert "Nothing attached" in str(screen.hint.render())

        await attach(pilot, screen, tmp_path / "one.md", tmp_path / "two.md")

        await pilot.press("g", "f")
        await pilot.pause()
        assert screen.picking_files
        assert str(screen.hint.render()) == screen.hint_for(MODE_NORMAL, True)
        assert "jö/kl pick" in str(screen.hint.render())

        # The motions the panes behind the window use, on a line of files
        assert screen.files.picked == 1
        await pilot.press("j")
        await pilot.pause()
        assert screen.files.picked == 0
        await pilot.press("j")
        await pilot.pause()
        assert screen.files.picked == 0
        await pilot.press("ö")
        await pilot.pause()
        assert screen.files.picked == 1

        # Back to the text, with the cursor exactly where it was left
        await pilot.press("escape")
        await pilot.pause()
        assert not screen.picking_files
        assert screen.editor.has_focus
        assert screen.editor.cursor_location == (0, len("some words") - 1)
        assert str(screen.hint.render()) == screen.hint_for(MODE_NORMAL)
        assert "jö/kl move" in str(screen.hint.render())


async def test_escape_out_of_the_files_does_not_close_the_note(tmp_path):
    async with run_pilot() as pilot:
        screen = await open_note(pilot)

        await pilot.press("escape")
        await attach(pilot, screen, tmp_path / "one.md")

        await pilot.press("g", "f")
        await pilot.press("escape")
        await pilot.pause()

        assert pilot.app.screen is screen


async def test_enter_opens_the_file_that_is_picked_out(tmp_path):
    async with run_pilot() as pilot:
        opened = []
        screen = await open_note(pilot)
        report = tmp_path / "Q3 report.pdf"

        with patch(
            "todooit.ui.screens.note.screens.screen.open_path",
            lambda path: opened.append(path) or Opened.OK,
        ):
            await pilot.press("escape")
            await attach(pilot, screen, report)

            await pilot.press("g", "f", "enter")
            await pilot.pause()

            assert opened == [report]
            assert "Opening Q3 report.pdf" in str(screen.hint.render())


async def test_xx_detaches_the_file_that_is_picked_out(tmp_path):
    async with run_pilot() as pilot:
        screen = await open_note(pilot)

        await pilot.press(*list("some words"))
        await pilot.press("escape")
        await attach(pilot, screen, tmp_path / "one.md", tmp_path / "two.md")

        await pilot.press("g", "f", "j")          # onto the first of the two
        await pilot.press("x", "x")
        await pilot.pause()

        assert screen.files.paths == [tmp_path / "two.md"]
        assert screen.todo.attachments == str(tmp_path / "two.md")
        assert "Detached one.md" in str(screen.hint.render())

        # The note itself never noticed
        assert screen.editor.text == "some words"

        # A single `x` is half a key and does nothing on its own
        await pilot.press("x")
        await pilot.pause()
        assert screen.files.paths == [tmp_path / "two.md"]

        # The last one out takes the strip off the page with it
        await pilot.press("x", "x")
        await pilot.pause()

        assert screen.files.paths == []
        assert not screen.files.display
        assert not screen.picking_files


async def test_the_strip_grows_a_row_rather_than_hiding_a_file(tmp_path):
    """Everything attached is on the page, however many there are"""

    async with run_pilot() as pilot:
        screen = await open_note(pilot)
        names = [f"a file with a longish name {index}.md" for index in range(8)]

        await pilot.press("escape")
        await attach(pilot, screen, *(tmp_path / name for name in names))
        await pilot.pause()

        strip = screen.files

        assert len(strip.rows) > 1
        assert sorted(index for row in strip.rows for index in row) == list(range(8))
        assert strip.size.height == len(strip.rows)

        for name in names:
            assert name in drawn(screen)

        # Up and down walk the rows, and up off the top row is the way out
        await pilot.press("g", "f")
        await pilot.pause()
        assert strip.row_of(strip.picked) == len(strip.rows) - 1

        await pilot.press("k")
        await pilot.pause()
        assert strip.row_of(strip.picked) == len(strip.rows) - 2

        await pilot.press("l")
        await pilot.pause()
        assert strip.row_of(strip.picked) == len(strip.rows) - 1

        for _ in range(len(strip.rows)):
            await pilot.press("k")
            await pilot.pause()

        assert not screen.picking_files


async def test_a_file_that_is_gone_is_offered_for_detaching(tmp_path):
    async with run_pilot() as pilot:
        screen = await open_note(pilot)

        await pilot.press("escape")
        await attach(pilot, screen, tmp_path / "moved away.md")

        await pilot.press("g", "f", "enter")
        await pilot.pause()

        assert screen.awaiting_answer
        assert "is gone" in str(screen.hint.render())

        await pilot.press("y")
        await pilot.pause()

        assert not screen.awaiting_answer
        assert screen.files.paths == []


async def test_the_pinned_note_carries_files_too(tmp_path):
    async with run_pilot() as pilot:
        await boot(pilot)

        await pilot.press("m")
        await pilot.pause()

        screen = pilot.app.screen
        assert isinstance(screen, PinnedNoteScreen)

        await attach(pilot, screen, tmp_path / "scratch.md")

        assert PinnedNote.get_attachments() == str(tmp_path / "scratch.md")
