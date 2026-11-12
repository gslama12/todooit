"""
The projects pane is as wide as its widest row, with every project expanded

The split between the panes follows the project tree rather than holding at a
fixed share: the widest row the tree could ever draw sets it, so folding a
project never moves it, and the gap after that row matches the one in front of
it. A share of the screen caps it, past which long names wrap.
"""

from rich.cells import cell_len

from tests.test_ui.ui_base import boot, commit_line, new_project, run_pilot
from todooit.ui.pane_layout import GUIDE_BRANCH
from todooit.ui.screens.index import DualSplit
from todooit.ui.widgets.renderers.base_renderer import COLUMN_PADDING
from todooit.ui.widgets.trees.projects_tree import ProjectsTree

# The size run_pilot opens the app at
SCREEN_WIDTH = 120

# The folder every stored project is drawn with, and the space after it
ICON = "󰉋 "


def row_width(name: str, depth: int = 0) -> int:
    """Cells a project row takes: its padding either side, guides, icon and name"""

    return 2 * COLUMN_PADDING + depth * len(GUIDE_BRANCH) + cell_len(ICON + name)


def pane_width(tree: ProjectsTree) -> int:
    """The pane's inner width, scrollbar included: what the rows are given"""

    return tree.size.width


async def settle(pilot) -> None:
    for _ in range(4):
        await pilot.pause()


async def test_pane_fits_widest_row():
    async with run_pilot() as pilot:
        app = await boot(pilot)
        tree = app.project_tree

        name = "a longer project"
        await new_project(pilot, name)
        await settle(pilot)

        assert pane_width(tree) == row_width(name)


async def test_pane_narrows_when_widest_row_goes():
    async with run_pilot() as pilot:
        app = await boot(pilot)
        tree = app.project_tree

        await new_project(pilot, "short")
        await settle(pilot)
        narrow = pane_width(tree)

        # A rename starts from an empty field, so the whole name is typed
        longer = "short, now longer"
        await pilot.press("e", "c", "c")
        await commit_line(pilot, longer)
        await settle(pilot)

        assert pane_width(tree) == row_width(longer)

        await pilot.press("e", "c", "c")
        await commit_line(pilot, "short")
        await settle(pilot)

        assert pane_width(tree) == narrow


async def test_folding_keeps_the_width():
    """A collapsed project still counts its hidden children"""

    async with run_pilot() as pilot:
        app = await boot(pilot)
        tree = app.project_tree

        await new_project(pilot, "parent")
        child = "a longer child"
        await pilot.press("N")
        await commit_line(pilot, child)
        await settle(pilot)

        expanded = pane_width(tree)
        assert expanded == row_width(child, depth=1)

        # Back to the parent and fold it
        await pilot.press("k", "h")
        await settle(pilot)

        parent = tree.current_model
        assert parent.description == "parent"
        assert not app.api.is_expanded(parent)
        assert pane_width(tree) == expanded


async def test_width_is_capped_to_a_share_of_the_screen():
    async with run_pilot() as pilot:
        app = await boot(pilot)
        tree = app.project_tree
        split = app.screen.query_one(DualSplit)

        await new_project(pilot, "x" * 100)
        await settle(pilot)

        cap = int(SCREEN_WIDTH * app.api.vars.projects_pane_max_width)
        switcher = app.screen.query_one("#project_switcher")
        assert tree.outer_size.width + switcher.styles.margin.width == cap

        # The cap is a share of the screen, so it follows a resize
        await pilot.resize_terminal(80, 36)
        await settle(pilot)

        cap = int(80 * app.api.vars.projects_pane_max_width)
        columns = split.styles.grid_columns
        assert columns is not None
        assert columns[0].value == cap


async def test_fixed_split_when_auto_width_is_off():
    async with run_pilot() as pilot:
        app = await boot(pilot)
        split = app.screen.query_one(DualSplit)

        app.api.vars.projects_pane_auto_width = False
        split.fit_projects_pane()
        await settle(pilot)

        columns = split.styles.grid_columns
        assert columns is not None
        assert [(c.value, c.unit.name) for c in columns] == [
            (1.0, "FRACTION"),
            (3.0, "FRACTION"),
        ]


async def test_expanding_never_puts_the_scrollbar_up():
    """
    Unfolding a project in a pane that still fits leaves no scrollbar to paint

    The new rows go in before the blank run holding the Bin to the floor is
    shortened to make room, so for a moment the pane overflows. That
    moment has to be over before the frame is drawn, or the scrollbar flashes
    up (and the split widens a column to fit it) on every unfold.
    """

    async with run_pilot() as pilot:
        app = await boot(pilot)
        tree = app.project_tree

        await new_project(pilot, "parent")
        await pilot.press("N")
        # Children wider than their parent with its count, as in any real tree
        await commit_line(pilot, "first child")
        for name in ("second child", "third child"):
            await pilot.press("n")
            await commit_line(pilot, name)

        await pilot.press("k", "k", "k", "h")
        await settle(pilot)
        assert tree.current_model.description == "parent"
        width = pane_width(tree)

        for _ in range(2):
            # Synchronously, before any frame: nothing has been painted yet
            tree.toggle_expand()
            assert not tree.show_vertical_scrollbar

            await settle(pilot)
            assert not tree.show_vertical_scrollbar
            assert pane_width(tree) == width
