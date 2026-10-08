from textual.widgets import ContentSwitcher

from tests.test_ui.ui_base import boot, run_pilot, visible_todos
from todooit.api import TODAY
from todooit.ui.tui import Todooit
from todooit.ui.widgets.trees.fixed_todos_tree import FixedTodosTree


async def test_startup():
    async with run_pilot() as pilot:
        app = pilot.app
        assert isinstance(app, Todooit)

        assert app.is_running

        # check for vars
        assert app.bar_switcher is not None
        assert app.project_tree is not None

        assert app.get_todooit_mode() == "NORMAL"


async def test_pane_lookups():
    """
    The app finds the panes, and the config's `api.vars` hands on the same
    ones: the tasks pane in front, or None once the empty pane is back up
    """

    async with run_pilot() as pilot:
        app = await boot(pilot)

        assert app.api.vars.projects_tree is app.project_tree
        assert app.bar is app.bar_switcher.status_bar

        today = visible_todos(app)
        assert app.todos_tree is today
        assert app.api.vars.todos_tree is today

        switcher = app.screen.query_one("#todo_switcher", expect_type=ContentSwitcher)
        switcher.current = "empty-pane"
        await pilot.pause()

        assert app.todos_tree is None
        assert app.api.vars.todos_tree is None


async def test_mode_follows_editing():
    """The bar's mode pill: NORMAL on the trees, INSERT inside an edit"""

    async with run_pilot() as pilot:
        app = await boot(pilot)

        assert app.get_todooit_mode() == "NORMAL"

        await pilot.press("j", "n")
        await pilot.pause()
        assert app.get_todooit_mode() == "INSERT"

        await pilot.press(*list("project"))
        await pilot.press("enter")
        await pilot.pause()
        assert app.get_todooit_mode() == "NORMAL"


async def test_todooit_opens_on_today():
    """The day's work is the first thing on screen, focused"""

    async with run_pilot() as pilot:
        app = await boot(pilot)

        tree = app.focused
        assert isinstance(tree, FixedTodosTree)
        assert tree.model is TODAY

        # The projects cursor points at the same place the pane shows
        assert app.project_tree.current_model is TODAY
