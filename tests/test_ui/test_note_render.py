"""
Notes are stored as markdown: written as typed, drawn rendered off the cursor line
"""

import pytest
from textual.geometry import Offset

from tests.test_ui.test_note_ui import open_note
from tests.test_ui.ui_base import run_pilot, set_clipboard
from todooit.api import Todo
from todooit.ui.screens.note.disp.markup import (
    BOLD,
    BOLD_ITALIC,
    BULLET_SPANS,
    HEADER_SPANS,
    HIGHLIGHT,
    ITALIC,
    MARKER,
    RULE,
    RULE_SPAN,
    capitals,
    draw_line,
    scan_note,
)
from todooit.ui.screens.note.vim.modes import MODE_INSERT, MODE_NORMAL

LONG_TEXT = "a line of words long enough to wrap around the window more than once " * 6


def body_of(editor, y: int):
    """Row `y` of the window as drawn, gutter off."""

    return editor.render_line(y).crop(editor.gutter_width)


def text_at(editor, y: int) -> str:
    return body_of(editor, y).text


async def leave(pilot) -> None:
    await pilot.press("escape", "escape")
    await pilot.pause()


async def load(pilot, text: str, cursor_row: int = 0):
    """A note window on `text`, with the cursor standing on `cursor_row`."""

    screen = await open_note(pilot)
    editor = screen.editor

    editor.load_text(text)
    editor.move_cursor((cursor_row, 0))
    await pilot.pause()

    return screen, editor


@pytest.mark.parametrize(
    "typed",
    ["- item", "* item", "1. item", "> quoted", "# title", "## title", "---", "*x*", "**x**"],
)
async def test_what_is_typed_is_what_is_stored(typed):
    async with run_pilot() as pilot:
        screen = await open_note(pilot)

        await pilot.press("escape", "i")
        await pilot.press(*list(typed))

        assert screen.editor.text == typed
        assert screen.editor.cursor_location == (0, len(typed))

        await leave(pilot)

        assert Todo.all()[0].note == typed


async def test_bullets_are_drawn_by_depth_off_the_cursor_line():
    written = "top\n- a\n  - b\n    - c\n      - d\n* e"

    async with run_pilot() as pilot:
        _, editor = await load(pilot, written)

        assert [text_at(editor, y).rstrip() for y in range(1, 6)] == [
            "• a",
            "  ◦ b",
            "    ▪ c",
            "      ▪ d",
            "• e",
        ]
        assert editor.text == written

        await leave(pilot)


@pytest.mark.parametrize("mode_keys, mode", [((), MODE_NORMAL), (("i",), MODE_INSERT)])
async def test_the_cursor_line_is_raw_and_the_rest_stays_rendered(mode_keys, mode):
    async with run_pilot() as pilot:
        screen, editor = await load(pilot, "- one\n> two\n# three\n*four*\n- five")

        await pilot.press("escape")
        await pilot.press(*mode_keys)
        assert editor.mode == mode

        drawn = [text_at(editor, y).rstrip() for y in range(5)]
        assert drawn == ["- one", "▎ two", "THREE", "four", "• five"]

        editor.move_cursor((2, 0))
        await pilot.pause()

        drawn = [text_at(editor, y).rstrip() for y in range(5)]
        assert drawn == ["• one", "▎ two", "# three", "four", "• five"]

        editor.move_cursor((3, 0))
        await pilot.pause()

        assert text_at(editor, 3).rstrip() == "*four*"
        assert text_at(editor, 2).rstrip() == "THREE"

        await leave(pilot)


def test_numbered_items_keep_their_depth_colours():
    spans = list(scan_note(["1. a", "  1. b"]))

    assert spans[0] == [(0, 3, BULLET_SPANS[0])]
    assert spans[1] == [(2, 5, BULLET_SPANS[1])]


async def test_a_numbered_item_is_drawn_as_written():
    async with run_pilot() as pilot:
        _, editor = await load(pilot, "top\n1. a\n2. b")

        assert text_at(editor, 1).rstrip() == "1. a"
        assert text_at(editor, 2).rstrip() == "2. b"

        await leave(pilot)


async def test_a_wrapped_quote_has_its_bar_on_every_row():
    async with run_pilot() as pilot:
        _, editor = await load(pilot, "top\n> " + LONG_TEXT)

        rows = len(editor.wrapped_document.get_offsets(1)) + 1
        assert rows > 1

        for y in range(1, rows + 1):
            assert text_at(editor, y).startswith("▎"), y

        await leave(pilot)


@pytest.mark.parametrize(
    "level, drawn", [("#", "PLAN"), ("##", "Plan"), ("######", "Plan")]
)
async def test_a_heading_is_one_washed_row_with_no_line_under_it(level, drawn):
    async with run_pilot() as pilot:
        _, editor = await load(pilot, f"top\n{level} Plan\nbelow")

        assert text_at(editor, 1).rstrip() == drawn
        assert text_at(editor, 2).rstrip() == "below"

        strip = body_of(editor, 1)
        wash = {segment.style.bgcolor for segment in strip}

        assert strip.cell_length == editor.scrollable_content_region.width - editor.gutter_width
        assert len(wash) == 1
        assert wash != {editor._theme.base_style.bgcolor}
        assert not any(segment.style.underline for segment in strip)

        # The washing stops at the heading
        assert {segment.style.bgcolor for segment in body_of(editor, 2)} == {
            editor._theme.base_style.bgcolor
        }

        await leave(pilot)


def test_each_level_has_its_color_up_to_the_third():
    assert list(scan_note(["# a"])) == [[(0, 1, HEADER_SPANS[0])]]
    assert list(scan_note(["## a"])) == [[(0, 1, HEADER_SPANS[1])]]
    assert list(scan_note(["### a"])) == [[(0, 1, HEADER_SPANS[2])]]
    assert list(scan_note(["#### a"])) == [[(0, 1, HEADER_SPANS[2])]]
    assert list(scan_note(["###### a b"])) == [[(0, 3, HEADER_SPANS[2])]]


def test_emphasis_is_read_inside_a_title():
    assert list(scan_note(["## a *b*"])) == [[(0, 3, HEADER_SPANS[1]), (2, 3, ITALIC)]]
    assert list(scan_note(["# **a** b"])) == [[(0, 3, HEADER_SPANS[0]), (0, 1, BOLD)]]


def test_a_rule_reads_no_emphasis():
    assert list(scan_note(["---"])) == [[(0, 3, RULE_SPAN)]]


async def test_the_three_levels_look_different_and_the_first_is_blue():
    async with run_pilot() as pilot:
        _, editor = await load(pilot, "top\n# a\n## b\n### c\n#### d")

        def looks(y: int) -> tuple:
            style = next(iter(body_of(editor, y))).style
            return style.color, style.bgcolor

        assert looks(1)[0].name == pilot.app.api.vars.theme.blue.lower()
        assert len({looks(1), looks(2), looks(3)}) == 3
        assert looks(4) == looks(3)

        await leave(pilot)


async def test_only_the_top_level_is_drawn_in_capitals():
    async with run_pilot() as pilot:
        _, editor = await load(pilot, "top\n# Plan b\n## Plan b\n### Plan b")

        assert [text_at(editor, y).rstrip() for y in (1, 2, 3)] == [
            "PLAN B",
            "Plan b",
            "Plan b",
        ]

        await leave(pilot)


async def test_capitals_are_only_how_a_heading_is_drawn():
    written = "top\n# Plan b"

    async with run_pilot() as pilot:
        screen, editor = await load(pilot, written)

        assert text_at(editor, 1).rstrip() == "PLAN B"
        assert editor.text == written

        # As written on the cursor line, on the letter that was drawn there
        editor.move_cursor((1, 3))
        await pilot.pause()

        assert text_at(editor, 1).rstrip() == "# Plan b"
        assert editor.cursor_location == (1, 5)

        await leave(pilot)

        assert Todo.all()[0].note == written


def test_capitals_keep_a_lines_columns():
    # `ß` has no one-character capital; a longer one would move every column
    assert draw_line("# straße [site](https://example.com)") == "STRAßE SITE"
    assert capitals("ß") == "ß"


async def test_a_raw_heading_keeps_its_wash_and_shows_the_cursor():
    async with run_pilot() as pilot:
        _, editor = await load(pilot, "# Plan\nbelow")

        # NORMAL's block: INSERT's cursor is the terminal's own
        await pilot.press("escape")
        await pilot.pause()

        assert text_at(editor, 0).rstrip() == "# Plan"

        strip = body_of(editor, 0)
        cursor = editor._theme.cursor_style.bgcolor
        rest = [s for s in strip if s.style.bgcolor != cursor]

        assert any(s.style.bgcolor == cursor for s in strip)
        assert len({s.style.bgcolor for s in rest}) == 1
        assert rest[0].style.bgcolor != editor._theme.base_style.bgcolor

        await leave(pilot)


async def test_a_long_heading_stays_on_one_row():
    async with run_pilot() as pilot:
        _, editor = await load(pilot, "top\n# " + LONG_TEXT + "\nbelow")

        assert editor.wrapped_document.get_offsets(1) == []
        assert text_at(editor, 2).rstrip() == "below"
        assert (
            body_of(editor, 1).cell_length
            == editor.scrollable_content_region.width - editor.gutter_width
        )

        # On the cursor line it's text like any other, and wraps
        editor.move_cursor((1, 0))
        await pilot.pause()

        assert len(editor.wrapped_document.get_offsets(1)) > 0

        await leave(pilot)


async def test_a_rule_is_drawn_across_the_window():
    async with run_pilot() as pilot:
        _, editor = await load(pilot, "top\n---\nbelow")

        width = editor.scrollable_content_region.width - editor.gutter_width

        assert text_at(editor, 1) == RULE * width
        assert editor.text == "top\n---\nbelow"

        # Raw once the cursor stands on it, a rule again once it leaves
        editor.move_cursor((1, 0))
        await pilot.pause()
        assert text_at(editor, 1).rstrip() == "---"

        editor.move_cursor((0, 0))
        await pilot.pause()
        assert text_at(editor, 1) == RULE * width

        await leave(pilot)


def test_a_raw_rule_is_still_faint():
    assert list(scan_note(["---"], raw_rows=(0,))) == [[(0, 3, RULE_SPAN)]]


@pytest.mark.parametrize(
    "line, span",
    [
        ("say *this* twice", ITALIC),
        ("say _this_ twice", ITALIC),
        ("say **this** twice", BOLD),
        ("say __this__ twice", BOLD),
        ("say ***this*** twice", BOLD_ITALIC),
        ("say ___this___ twice", BOLD_ITALIC),
        ("say ==this== twice", HIGHLIGHT),
    ],
)
def test_emphasis_is_lit_with_its_marks_off_the_page(line, span):
    assert list(scan_note([line])) == [[(4, 8, span)]]
    assert draw_line(line) == "say this twice"


def test_bold_and_italic_on_one_line_keep_apart():
    assert list(scan_note(["*a* **b** _c_"])) == [[(0, 1, ITALIC), (2, 3, BOLD), (4, 5, ITALIC)]]


@pytest.mark.parametrize(
    "line, raw, span",
    [("a **b**", 4, BOLD), ("a *b*", 3, ITALIC), ("a _b_", 3, ITALIC)],
)
def test_emphasis_on_the_cursor_line_keeps_its_marks(line, raw, span):
    marks = len(line) - raw - 1
    spans = list(scan_note([line], raw_rows=(0,)))[0]

    assert (raw, raw + 1, span) in spans
    assert (2, 2 + marks, MARKER) in spans
    assert (raw + 1, len(line), MARKER) in spans


def test_a_highlight_on_the_cursor_line_keeps_its_marks():
    spans = list(scan_note(["a ==b=="], raw_rows=(0,)))[0]

    assert (4, 5, HIGHLIGHT) in spans
    assert (2, 4, MARKER) in spans
    assert (5, 7, MARKER) in spans


@pytest.mark.parametrize(
    "line",
    ["a == b == c", "a==b and c==d", "=== x", "==open", "====x====", "x ==y==z"],
)
def test_equals_signs_that_highlight_nothing_stay_on_the_page(line):
    assert list(scan_note([line])) == [[]]
    assert draw_line(line) == line


@pytest.mark.parametrize(
    "line",
    ["snake_case_name", "a_b_ c", "_open", "a _ b _ c", "__init__x"],
)
def test_underscores_inside_words_are_no_markup(line):
    assert list(scan_note([line])) == [[]]
    assert draw_line(line) == line


async def test_stars_that_pair_nothing_stay_on_the_page():
    async with run_pilot() as pilot:
        lines = ["top", "2 * 3 * 4", "* not closed", "*open", "[a*b](https://x.io/a*b)"]
        _, editor = await load(pilot, "\n".join(lines))

        assert text_at(editor, 1).rstrip() == "2 * 3 * 4"
        assert text_at(editor, 2).rstrip() == "• not closed"
        assert text_at(editor, 3).rstrip() == "*open"
        assert text_at(editor, 4).rstrip() == "a*b"

        await leave(pilot)


async def test_no_new_markup_is_read():
    lines = ["top", "- [ ] box", "```", "`code`", "=== x"]

    async with run_pilot() as pilot:
        _, editor = await load(pilot, "\n".join(lines))

        assert text_at(editor, 1).rstrip() == "• [ ] box"

        for row in range(2, len(lines)):
            assert text_at(editor, row).rstrip() == lines[row]

        await leave(pilot)


async def test_a_click_on_a_rendered_line_lands_on_the_character_clicked():
    async with run_pilot() as pilot:
        _, editor = await load(pilot, "top\n# Title\nsay **this** now\n- item")

        async def click(row: int, column: int) -> None:
            region = editor.content_region
            await pilot.click(
                offset=Offset(region.x + editor.gutter_width + column, region.y + row)
            )
            await pilot.pause()

        await click(1, 2)  # the `t` of `Title`
        assert editor.cursor_location == (1, len("# Ti"))

        await click(2, 5)  # the `h` of `this`
        assert editor.cursor_location == (2, len("say **t"))

        await click(3, 2)  # the `i` of `item`
        assert editor.cursor_location == (3, len("- "))

        await leave(pilot)


async def test_moving_down_lands_on_the_stored_column():
    async with run_pilot() as pilot:
        _, editor = await load(pilot, "0123456789\n**bold** words")
        await pilot.press("escape")
        editor.move_cursor((0, 6))
        await pilot.pause()

        editor.action_cursor_down()
        await pilot.pause()

        # Column 6 of what was drawn, `bold words`, is that `o` of what's stored
        assert editor.cursor_location == (1, len("**bold** w"))

        await leave(pilot)


async def test_joining_up_to_a_rendered_line_keeps_its_stored_text():
    async with run_pilot() as pilot:
        _, editor = await load(pilot, "say *this*\nmore", cursor_row=1)

        await pilot.press("escape", "i", "backspace")
        await pilot.pause()

        assert editor.text == "say *this*more"

        await leave(pilot)


async def test_enter_and_tab_write_markdown_and_not_glyphs():
    async with run_pilot() as pilot:
        screen = await open_note(pilot)
        editor = screen.editor

        await pilot.press("escape", "i")
        await pilot.press(*list("- one"), "enter", *list("two"), "tab")
        await pilot.pause()

        assert editor.text == "- one\n  - two"

        await leave(pilot)


async def test_renumbering_sees_the_whole_list_through_rendered_rows():
    async with run_pilot() as pilot:
        _, editor = await load(pilot, "1. a\n- b\n1. c\n1. d", cursor_row=2)

        await pilot.press("escape", "i")
        editor.move_cursor((2, len("1. c")))
        await pilot.press("enter", "x")
        await pilot.pause()

        assert editor.text == "1. a\n- b\n1. c\n2. x\n3. d"

        await leave(pilot)


async def test_a_paste_stores_markdown():
    async with run_pilot() as pilot:
        screen = await open_note(pilot)
        editor = screen.editor

        set_clipboard("## Plan\n* one\n> said\n***")
        await pilot.press("ctrl+v")
        await pilot.pause()

        # A rule straight under words would read as their underline elsewhere
        assert editor.text == "## Plan\n- one\n> said\n\n---"

        await leave(pilot)


async def test_a_copy_hands_out_what_is_stored():
    async with run_pilot() as pilot:
        _, editor = await load(pilot, "# Plan\n1. a\n  - b\n> *said*")

        await pilot.press("ctrl+c")
        await pilot.pause()

        assert pilot.app.clipboard == "# Plan\n1. a\n  - b\n> *said*"

        await leave(pilot)


async def test_backspace_takes_a_star_like_any_other_character():
    async with run_pilot() as pilot:
        _, editor = await load(pilot, "say *this*")

        await pilot.press("escape", "i")
        editor.move_cursor((0, len("say *this*")))
        await pilot.press("backspace")
        await pilot.pause()

        assert editor.text == "say *this"

        await leave(pilot)


@pytest.mark.parametrize(
    "line, typed",
    [
        ("- a *b*", "- Q*b*"),
        ("- a [n](https://x.io/y)", "- Q[n](https://x.io/y)"),
    ],
)
async def test_enter_in_front_of_hidden_markup_stays_in_front_of_it(line, typed):
    async with run_pilot() as pilot:
        _, editor = await load(pilot, line)

        await pilot.press("escape", "i")
        editor.move_cursor((0, len("- a ")))
        await pilot.press("enter", "Q")
        await pilot.pause()

        assert editor.text == "- a \n" + typed

        await leave(pilot)


@pytest.mark.parametrize("opening", ["> ", "  > ", "> *"])
async def test_a_quote_of_one_long_word_has_its_bar_on_every_row(opening):
    async with run_pilot() as pilot:
        _, editor = await load(pilot, "top\n" + opening + "a" * 300)

        rows = len(editor.wrapped_document.get_offsets(1)) + 1
        assert rows > 1

        for y in range(1, rows + 1):
            assert "▎" in text_at(editor, y), y

        await leave(pilot)


async def test_a_long_rule_wraps_once_the_cursor_stands_on_it():
    async with run_pilot() as pilot:
        _, editor = await load(pilot, "top\n" + "-" * 300)

        assert editor.wrapped_document.get_offsets(1) == []

        editor.move_cursor((1, 0))
        await pilot.pause()

        assert len(editor.wrapped_document.get_offsets(1)) > 0

        await leave(pilot)


def test_four_stars_are_no_markup():
    assert list(scan_note(["****x****"])) == [[]]


async def test_a_selection_is_lit_like_a_field_being_edited():
    """Inverted accent, as a description being edited draws one, not a faint wash"""

    async with run_pilot() as pilot:
        screen = await open_note(pilot)
        theme = pilot.app.api.vars.theme
        style = screen.editor._theme.selection_style

        assert style.bgcolor.name == theme.secondary.lower()
        assert style.color.name == theme.background1.lower()


async def test_the_note_sits_flush_on_a_screen_of_its_own_color():
    """A round border's cells wear the note's background; the screen does too"""

    async with run_pilot() as pilot:
        screen = await open_note(pilot)
        frame = screen.query_one("NoteFrame")

        assert screen.styles.background == frame.styles.background
