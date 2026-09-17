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
    LINK,
    MARKER,
    MODE_INSERT,
    MODE_NORMAL,
    QUOTE,
    QUOTE_BAR,
    QUOTE_GLYPH,
    QUOTE_ITEM,
    RULE,
    RULE_SPAN,
    NoteScreen,
    NoteScreenBase,
    build_theme,
    scan_note,
)
from todooit.ui.screens.pinned_note import PinnedNoteScreen
from todooit.utils.links import fold_links
from tests.test_ui.ui_base import (
    boot,
    commit_line,
    create_and_move_to_todo,
    run_pilot,
    set_clipboard,
)

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
    """Both are written rather than pressed, and both are drawn as typed"""

    async with run_pilot() as pilot:
        screen = await open_note(pilot)

        # markdown's own `- `, and emphasis wrapped in markdown's own stars -
        # which are swapped for the marks that cost no columns on the way in,
        # exactly as the dash is swapped for the bullet
        await pilot.press(*list("- say *this* twice"))
        assert screen.editor.text == (
            "• say " + EMPH_MARK + "this" + EMPH_MARK + " twice"
        )

        names = [name for _, _, name in list(scan_note([screen.editor.text]))[0]]

        assert names[0] == "note-bullet-0"
        assert EMPH in names

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

    theme = build_theme(DooitThemeBase)
    marker = theme.syntax_styles[MARKER].color.triplet

    assert marker != theme.base_style.bgcolor.triplet
    assert marker != theme.syntax_styles[EMPH].color.triplet


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


async def test_typing_a_quote_marker_after_an_indent():
    """markdown puts the mark after the indent; so does this"""

    async with run_pilot() as pilot:
        screen = await open_note(pilot)

        await pilot.press("tab")
        await pilot.press(*list("> indented"))
        assert screen.editor.text == "  " + QUOTE_GLYPH + "indented"

        await pilot.press("escape", "escape")
        await pilot.pause()


async def test_typing_a_bullet_marker():
    async with run_pilot() as pilot:
        screen = await open_note(pilot)

        # markdown's `- ` goes in, the bullet it stands for comes out
        await pilot.press(*list("- "))
        assert screen.editor.text == "\u2022 "

        await pilot.press(*list("first"))

        # Enter carries it on, the way it carries a typed bullet on
        await pilot.press("enter")
        await pilot.press(*list("second"))
        assert screen.editor.text == "\u2022 first\n\u2022 second"

        await pilot.press("escape", "escape")
        await pilot.pause()


async def test_a_star_opens_a_bullet_too():
    """markdown's other list mark, arriving as the one glyph the note draws"""

    async with run_pilot() as pilot:
        screen = await open_note(pilot)

        await pilot.press(*list("* item"))
        assert screen.editor.text == "• item"

        await pilot.press("escape", "escape")
        await pilot.pause()


async def test_a_star_pair_at_the_head_of_a_line_costs_no_column():
    """
    The bug: a `*` painted out to be unseen still took the column it was
    written in, so emphasis opening a line read as an indent that was not
    there. The pair is swapped for the zero-width marks the moment it closes,
    and what is left on the page is the words and nothing else
    """

    async with run_pilot() as pilot:
        screen = await open_note(pilot)

        await pilot.press(*list("*loud* and clear"))

        assert screen.editor.text == (
            EMPH_MARK + "loud" + EMPH_MARK + " and clear"
        )
        assert cell_len(screen.editor.text) == len("loud and clear")

        # The words are what is emphasised, and the two marks over the top of
        # them are the pair - drawn, and worth nothing on the page
        text = screen.editor.text
        spans = list(scan_note([text]))[0]

        assert [
            (text.encode()[start:end].decode(), name) for start, end, name in spans
        ] == [("loud", EMPH), (EMPH_MARK, MARKER), (EMPH_MARK, MARKER)]

        await pilot.press("escape", "escape")
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


async def test_backspace_next_to_a_mark_takes_the_emphasis_off():
    """
    The marks cannot be seen, so taking only the one backspace landed on would
    look like nothing happening and strand the other in the note for good
    """

    async with run_pilot() as pilot:
        screen = await open_note(pilot)

        await pilot.press(*list("say *this*"))
        assert screen.editor.text == "say " + EMPH_MARK + "this" + EMPH_MARK

        await pilot.press("backspace")
        assert screen.editor.text == "say this"
        assert screen.editor.cursor_location == (0, 8)

        # And what is typed next lands after the words, not inside them
        await pilot.press(*list(" twice"))
        assert screen.editor.text == "say this twice"

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


async def test_a_typed_bullet_follows_the_indent_it_is_typed_at():
    """The glyph says how deep the line sits, however the bullet got there"""

    async with run_pilot() as pilot:
        screen = await open_note(pilot)

        await pilot.press("tab")
        await pilot.press(*list("- nested"))
        assert screen.editor.text == "  \u25e6 nested"

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


async def test_dashes_still_reach_the_separator():
    """`- ` is a bullet, `---` is still a rule: the two never meet"""

    async with run_pilot() as pilot:
        screen = await open_note(pilot)

        await pilot.press(*list("---"))
        await pilot.pause()

        assert set(screen.editor.text) == {RULE}

        await pilot.press("escape", "escape")
        await pilot.pause()


async def test_a_bullet_opens_inside_a_quote():
    """A quote is a wrapper, not a kind of line: a list in one is still a list"""

    async with run_pilot() as pilot:
        screen = await open_note(pilot)

        await pilot.press(*list("> "))
        await pilot.press(*list("- quoted item"))
        assert screen.editor.text == QUOTE_GLYPH + "• quoted item"

        # Enter carries both markers on, so the list goes on inside the quote
        await pilot.press("enter")
        await pilot.press(*list("and another"))
        assert screen.editor.text == (
            QUOTE_GLYPH
            + "• quoted item\n"
            + QUOTE_GLYPH
            + "• and another"
        )

        await pilot.press("escape", "escape")
        await pilot.pause()


async def test_a_quoted_marker_is_green_rather_than_its_depth():
    """
    Inside a quote the color is spoken for - it says the line is quoted - so
    the glyph and the indent are left to say how deep the item sits
    """

    lines = [
        QUOTE_GLYPH + "• an item worth quoting",
        QUOTE_GLYPH + "  ◦ and one under it",
        QUOTE_GLYPH + "1. numbered, and quoted too",
    ]
    names = [[name for _, _, name in row] for row in scan_note(lines)]

    assert names == [[QUOTE, QUOTE_BAR, QUOTE_ITEM]] * 3

    theme = build_theme(DooitThemeBase)

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
            QUOTE_GLYPH + "• top\n" + QUOTE_GLYPH + "  ◦ child"
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

        written = QUOTE_GLYPH + "• item\n"

        await pilot.press("enter")
        assert screen.editor.text == written + QUOTE_GLYPH + "• "

        await pilot.press("enter")
        assert screen.editor.text == written + QUOTE_GLYPH

        await pilot.press("enter")
        assert screen.editor.text == written

        await pilot.press("escape", "escape")
        await pilot.pause()


async def test_a_quoted_line_is_green_behind_its_bar():
    line = QUOTE_GLYPH + "a snippet worth keeping"
    names = [name for _, _, name in list(scan_note([line]))[0]]

    assert names == [QUOTE, QUOTE_BAR]


async def test_a_long_link_is_styled_where_it_is_drawn():
    """
    The underline lands on the name the link is folded to, not on the address
    that name stands in for
    """

    line = QUOTE_GLYPH + "see " + LONG_LINK + " here"
    (spans,) = list(scan_note([line]))

    assert [name for _, _, name in spans] == [QUOTE, QUOTE_BAR, LINK]

    drawn, _ = fold_links(line)
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

        editor.load_text("a line\n" + QUOTE_GLYPH + "see " + LONG_LINK + " here")
        await pilot.pause()

        assert editor.document.get_line(1) == (
            QUOTE_GLYPH + "see " + LONG_LINK_DRAWN + " here"
        )

        # One row on the page: nothing has wrapped out from under the bar,
        # which is what used to take the link out of the block
        assert editor.wrapped_document.get_offsets(1) == []

        # And nothing was taken out of the note to get there
        assert LONG_LINK in editor.text

        await pilot.press("escape", "escape")
        await pilot.pause()


async def test_a_link_stays_folded_with_the_cursor_on_it():
    """
    The cursor is not what unfolds a link - nothing is. A note is read with
    the cursor somewhere in it, and a link that opened out under it would put
    the address back on the page exactly when it is being looked at
    """

    async with run_pilot() as pilot:
        screen = await open_note(pilot)
        editor = screen.editor

        editor.load_text(QUOTE_GLYPH + "see " + LONG_LINK + " here")
        await pilot.pause()

        folded = QUOTE_GLYPH + "see " + LONG_LINK_DRAWN + " here"

        for column in (0, 8, len(folded) - 1):
            editor.move_cursor((0, column))
            await pilot.pause()

            assert editor.document.get_line(0) == folded
            assert editor.wrapped_document.get_offsets(0) == []

        # And the whole of the address is still in the note behind it
        assert LONG_LINK in editor.text

        await pilot.press("escape", "escape")
        await pilot.pause()


async def test_a_name_is_edited_where_it_is_drawn():
    """
    What the fold hides is the markup, not the name: the words on the page are
    the words in the note, so they are retyped like any other words
    """

    async with run_pilot() as pilot:
        screen = await open_note(pilot)
        editor = screen.editor

        editor.load_text("see [the folder](" + LONG_LINK + ") here")
        await pilot.pause()

        assert editor.document.get_line(0) == "see the folder here"

        # Between "the " and "folder"
        editor.move_cursor((0, 8))
        await pilot.press(*list("big "))
        await pilot.pause()

        assert editor.document.get_line(0) == "see the big folder here"
        assert editor.text == "see [the big folder](" + LONG_LINK + ") here"

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


async def test_an_edit_reaching_into_a_link_takes_the_whole_of_it():
    """
    Half a link left on the line is not something that could be written back
    out as a note, so an edit that touches one swallows it
    """

    async with run_pilot() as pilot:
        screen = await open_note(pilot)
        editor = screen.editor

        editor.load_text("see [](" + LONG_LINK + ")")
        await pilot.pause()

        editor.move_cursor(editor.document.end)
        await pilot.press("backspace")
        await pilot.pause()

        assert editor.text == "see "

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


async def test_o_opens_a_folded_link_in_full():
    async with run_pilot() as pilot:
        opened = []

        with patch(
            "todooit.ui.screens.note.open_url",
            lambda url: opened.append(url) or True,
        ):
            screen = await open_note(pilot)
            editor = screen.editor

            editor.load_text("see [the folder](" + LONG_LINK + ") here")
            await pilot.pause()

            await pilot.press("escape")

            # Anywhere on the name it is drawn under
            editor.move_cursor((0, 6))
            await pilot.press("o")
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

        assert editor.text == "[](" + LONG_LINK + ")"
        assert editor.document.get_line(0) == LONG_LINK_DRAWN

        # Past the whole of it, where there is more of the note to write
        assert editor.cursor_location == (0, len(LONG_LINK_DRAWN))

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
    line = QUOTE_GLYPH + "see " + emphasised + " at https://example.com"
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


async def test_enter_in_front_of_a_bullet_opens_a_line_above():
    """
    The bug: `enter` from the head of a bullet wrote the marker out twice

    The prefix is carried onto the new line, so from column 0 the line below
    ended up as `• • item` - the marker it already had, behind a fresh one.
    From anywhere in front of the words the line moves down whole instead,
    with a blank one opening above it.
    """

    async with run_pilot() as pilot:
        screen = await open_note(pilot)
        editor = screen.editor

        await pilot.press(*list("- one"))
        await pilot.press("enter")
        await pilot.press(*list("two"))
        assert editor.text == "• one\n• two"

        # At the very start of the second bullet
        editor.move_cursor((1, 0))
        await pilot.press("enter")

        assert editor.text == "• one\n\n• two"
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
        assert editor.text == "• top\n  ◦ child"

        # In the indent of the nested line, short of its glyph
        editor.move_cursor((1, 1))
        await pilot.press("enter")

        assert editor.text == "• top\n\n  ◦ child"
        assert editor.cursor_location == (2, 1)

        # And between the glyph and the space that follows it
        editor.move_cursor((2, 3))
        await pilot.press("enter")

        assert editor.text == "• top\n\n\n  ◦ child"
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

        assert editor.text == "• \n• item"

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
        # and `# ` is how a header is meant on purpose
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


async def test_a_hash_draws_the_rule_the_title_is_typed_over():
    async with run_pilot() as pilot:
        screen = await open_note(pilot)

        await pilot.press(*list("# "))
        await pilot.pause()

        # The mark goes and the rule arrives; the title line is left empty,
        # with the cursor standing on it
        lines = screen.editor.text.splitlines()
        assert lines[0] == ""
        assert set(lines[1]) == {RULE}

        # Which is where the title is typed, and it is a title from its first
        # letter, because the rule saying so is already underneath it
        await pilot.press(*list("Section"))
        await pilot.pause()

        lines = screen.editor.text.splitlines()
        assert lines[0] == "Section"

        names = [name for row in scan_note(lines) for _, _, name in row]
        assert names == [HEADER, RULE_SPAN]

        await pilot.press("escape", "escape")
        await pilot.pause()


async def test_a_run_of_hashes_opens_the_one_header_there_is():
    """Every depth of markdown heading means heading; this note has one"""

    async with run_pilot() as pilot:
        screen = await open_note(pilot)

        await pilot.press(*list("### "))
        await pilot.pause()

        lines = screen.editor.text.splitlines()
        assert lines[0] == ""
        assert set(lines[1]) == {RULE}

        await pilot.press("escape", "escape")
        await pilot.pause()


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
