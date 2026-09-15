"""
How the cursor is drawn into a field that is being typed into

The cursor is a style laid over the cell it stands on, not a character put
into the buffer, so the text under it never moves. These tests hold that: the
letters keep their columns wherever the cursor is, and the field keeps one
width from the first keystroke to the last.
"""

from typing import Optional, Tuple

from todooit.api.theme import DooitThemeBase
from todooit.ui.widgets.inputs._input import Input

from tests.test_ui.ui_base import (
    boot,
    commit_line,
    create_and_move_to_todo,
    run_pilot,
)

THEME = DooitThemeBase


def editing(value: str, cursor: Optional[int] = None) -> Input:
    """A field mid-edit, with the cursor wherever it is asked for"""

    field = Input(value)
    field.is_editing = True

    # placed after the edit starts, since starting one selects the whole of
    # what is already there and a selection hides the cursor
    field._selection_anchor = None
    field._cursor_position = len(value) if cursor is None else cursor

    return field


def cursor_span(field: Input) -> Optional[Tuple[int, int]]:
    """Where the cursor block lands in what the field draws"""

    text = field.render_editing(THEME)
    style = Input.cursor_style(THEME)

    for span in text.spans:
        if span.style == style:
            return span.start, span.end

    return None


def test_the_cursor_puts_nothing_into_the_text():
    # every cursor position draws the same characters: only the styling moves
    for position in range(len("hello") + 1):
        assert editing("hello", position).render_editing(THEME).plain == "hello "


def test_the_cursor_covers_the_character_it_stands_on():
    assert cursor_span(editing("hello", 0)) == (0, 1)
    assert cursor_span(editing("hello", 3)) == (3, 4)


def test_the_cursor_past_the_end_sits_in_the_reserved_cell():
    field = editing("hello", 5)

    assert cursor_span(field) == (5, 6)
    assert field.render_editing(THEME).plain == "hello "


def test_an_empty_field_still_draws_a_cursor():
    field = editing("")

    assert field.render_editing(THEME).plain == " "
    assert cursor_span(field) == (0, 1)


def test_the_field_keeps_one_width_wherever_the_cursor_is():
    widths = {
        editing("hello", position).render_editing(THEME).cell_len
        for position in range(len("hello") + 1)
    }

    assert widths == {len("hello") + 1}


def test_spaces_at_either_end_are_drawn_as_typed():
    # stripping them would slide the line sideways as the cursor moved off
    field = editing("  padded  ", 0)

    assert field.render_editing(THEME).plain == "  padded   "


def test_a_selection_is_highlighted_instead_of_the_cursor():
    field = editing("hello", 5)
    field._selection_anchor = 0

    text = field.render_editing(THEME)
    spans = [(span.start, span.end, span.style) for span in text.spans]

    assert spans == [(0, 5, Input.selection_style(THEME))]
    assert cursor_span(field) is None


async def test_the_row_does_not_shift_as_the_cursor_moves():
    async with run_pilot() as pilot:
        tree = await create_and_move_to_todo(pilot)

        await pilot.press("n")
        await commit_line(pilot, "walk the dog")

        await pilot.press("i")
        await pilot.pause()

        component = tree.current._get_component("description")
        drawn = component.render_editing(tree.current.theme).plain

        for _ in range(len("walk the dog")):
            await pilot.press("left")
            assert component.render_editing(tree.current.theme).plain == drawn

        await pilot.press("escape")


async def test_a_project_name_is_drawn_as_the_buffer_holds_it():
    async with run_pilot() as pilot:
        app = await boot(pilot)

        await pilot.press("j", "n")
        await pilot.press(*list("two words"))
        await pilot.pause()

        renderer = app.project_tree.current
        component = renderer._get_component("description")

        # what is drawn is the buffer itself, with nothing wedged into it
        assert component.render_editing(renderer.theme).plain == "two words "

        await pilot.press("escape")
