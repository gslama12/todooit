"""
The highlighted row of the focused pane takes the color of the mode: the
panes' own NORMAL (NAV) keeps its highlight, a vim edit's NORMAL goes blue and
INSERT green, the colors the note's frame wears for them.
"""

from textual.color import Color

from tests.test_ui.test_vim_description import a_todo, an_empty_todo, engine
from tests.test_ui.ui_base import run_pilot
from todooit.ui.widgets.trees.model_tree import ModelTree
from todooit.vim_engine import MODE_INSERT, MODE_NORMAL

HIGHLIGHT = "option-list--option-highlighted"


def highlight(tree: ModelTree) -> Color:
    """The background the highlighted row is drawn on, as it ends up on screen."""

    style = tree.get_component_rich_style(HIGHLIGHT)
    assert style.bgcolor is not None
    return Color.from_rich_color(style.bgcolor)


def tinted(tree: ModelTree, name: str) -> Color:
    """The pane's background under the theme's `name` at 40%, as the CSS says."""

    theme = tree.api.vars.theme
    base = tree.styles.background
    return base + Color.parse(getattr(theme, name)).multiply_alpha(0.4)


async def test_nav_keeps_the_panes_highlight():
    async with run_pilot() as pilot:
        tree = await a_todo(pilot, "a todo")

        assert pilot.app.todooit_mode == "NORMAL"
        assert highlight(tree) == tinted(tree, "secondary")


async def test_a_vim_edits_normal_highlights_in_blue():
    async with run_pilot() as pilot:
        tree = await a_todo(pilot, "a todo")

        await pilot.press("e")
        await pilot.pause()

        assert engine(tree).mode == MODE_NORMAL
        assert highlight(tree) == tinted(tree, "blue")


async def test_insert_highlights_in_green_and_escape_goes_back_to_blue():
    async with run_pilot() as pilot:
        tree = await an_empty_todo(pilot)

        await pilot.press("e")
        await pilot.pause()
        assert engine(tree).mode == MODE_INSERT
        assert highlight(tree) == tinted(tree, "green")

        await pilot.press("x", "escape")
        await pilot.pause()
        assert engine(tree).mode == MODE_NORMAL
        assert highlight(tree) == tinted(tree, "blue")


async def test_leaving_the_edit_brings_the_nav_highlight_back():
    async with run_pilot() as pilot:
        tree = await a_todo(pilot, "a todo")

        await pilot.press("e")
        await pilot.pause()
        await pilot.press("escape")
        await pilot.pause()

        assert not tree.is_editing
        assert highlight(tree) == tinted(tree, "secondary")


async def test_an_edit_without_vim_keys_highlights_insert_in_green():
    async with run_pilot() as pilot:
        tree = await a_todo(pilot, "a todo")
        pilot.app.api.vim.descriptions = False

        await pilot.press("e")
        await pilot.pause()

        assert pilot.app.todooit_mode == "INSERT"
        assert highlight(tree) == tinted(tree, "green")

        await pilot.press("escape")
        await pilot.pause()
        assert highlight(tree) == tinted(tree, "secondary")
