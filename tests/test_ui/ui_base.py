from contextlib import contextmanager
from typing import Callable, List, Optional
from unittest.mock import patch

from textual.pilot import Pilot
from textual.widgets import ContentSwitcher
from textual.widgets.option_list import Option

from todooit.api import Project, Todo, fixed_project_from_id
from todooit.ui.tui import Todooit
from todooit.ui.widgets.trees.fixed_todos_tree import FixedTodosTree
from todooit.ui.widgets.trees.model_tree import ModelTree
from todooit.ui.widgets.trees.todos_tree import TodosTree

TEMP_DB_PATH = ":memory:"

# The host's clipboard, which a test can neither be handed nor allowed to
# write over. Patched once, for the whole run: what todooit reads back is what a
# test last put here, and nothing else on the machine can change it underneath
_clipboard = ""


def set_clipboard(text: str) -> None:
    global _clipboard
    _clipboard = text


patch("todooit.utils.clipboard.pyperclip.paste", lambda: _clipboard).start()
patch("todooit.utils.clipboard.pyperclip.copy", lambda text: None).start()


async def press_writing(pilot: Pilot, write: Callable[[], object]) -> None:
    """
    Presses a key whose only job is `write`, a plain model write

    Bound through the config's key API, the same way any config function
    reaches the database: nothing on this path asks a pane to redraw, so the
    panes catch up from the key's change signal alone. A model written
    outside a key press isn't redrawn until the next one.
    """

    app = pilot.app
    assert isinstance(app, Todooit)

    app.api.keys.set("<f9>", write)
    await pilot.press("f9")
    await pilot.pause()


def run_pilot():
    return Todooit(db_path=TEMP_DB_PATH).run_test(size=(120, 36))


async def boot(pilot: Pilot) -> Todooit:
    """
    Waits out the startup jump to the Today pane

    The app opens itself on Today with a `call_after_refresh`, so for the
    first few pauses of a test the cursor and the focus are still on their way
    there. Every test starts from the state the user actually sees: the Today
    pane in front, focused, and the projects cursor on the Today row.
    """

    app = pilot.app
    assert isinstance(app, Todooit)

    for _ in range(20):
        await pilot.pause()

        tree = visible_todos_or_none(app)
        if isinstance(tree, FixedTodosTree) and app.focused is tree:
            return app

    raise AssertionError("The app never settled on the Today pane")


def visible_todos_or_none(app: Todooit) -> Optional[TodosTree]:
    """The tasks pane in front, or None while the empty pane is showing"""

    content = app.screen.query_one(
        "#todo_switcher", expect_type=ContentSwitcher
    ).visible_content

    if isinstance(content, TodosTree):
        return content

    return None


def visible_todos(app: Todooit) -> TodosTree:
    tree = visible_todos_or_none(app)
    assert tree is not None, "No tasks pane is in front"
    return tree


async def commit_line(pilot: Pilot, text: str) -> None:
    """
    Types `text` into the open edit and commits it

    Enter is what keeps an edit; escape throws it away, and a brand new item
    thrown away without a name is dropped entirely.
    """

    if text:
        await pilot.press(*list(text))

    await pilot.press("enter")
    await pilot.pause()


async def new_project(pilot: Pilot, name: str) -> Project:
    """
    Creates a top-level project the way the user does: `j`, `n`, name, enter

    Leaves the cursor on the new project, with its (empty) tasks pane in
    front, and the projects pane focused.
    """

    app = pilot.app
    assert isinstance(app, Todooit)

    await pilot.press("j", "n")
    await commit_line(pilot, name)

    project = app.project_tree.current_model
    assert isinstance(project, Project)
    assert project.description == name

    return project


async def new_todo(pilot: Pilot, name: str) -> Todo:
    """
    Creates a todo in the open project's pane: `ö`, `n`, name, enter

    Assumes a stored project's pane is in front (the state `new_project`
    leaves behind). Leaves the cursor on the new todo, pane focused.
    """

    app = pilot.app
    assert isinstance(app, Todooit)

    await pilot.press("ö", "n")
    await commit_line(pilot, name)

    tree = visible_todos(app)
    todo = tree.current_model
    assert isinstance(todo, Todo)
    assert todo.description == name

    return todo


async def create_and_move_to_todo(pilot: Pilot) -> TodosTree:
    """
    A named project with its empty tasks pane in front and focused

    The smallest start most todo tests share.
    """

    app = await boot(pilot)
    await new_project(pilot, "project")
    await pilot.press("ö")
    await pilot.pause()

    tree = visible_todos(app)
    assert app.focused is tree

    return tree


def descriptions(tree: ModelTree) -> List[str]:
    """What the pane's stored rows say, top to bottom"""

    return [tree._renderers[o.id].model.description for o in tree_options(tree)]


async def reveal_project(pilot: Pilot, project) -> TodosTree:
    """
    Brings a project's own tasks pane back to the front, and hands it over

    What moving the projects cursor onto the project does, which is the only
    way a pane behind the one in front is ever looked at. A pane out of sight
    is not redrawn while it is out of sight -- the redraw it is owed is done
    at the moment it comes forward -- so a test reading one asks for it the
    way the user would rather than reaching past the switcher for the widget.
    """

    app = pilot.app
    assert isinstance(app, Todooit)

    app.api.vars.projects_tree.highlight_id(project.uuid)
    await pilot.pause()

    return visible_todos(app)


def tree_options(tree: ModelTree) -> List[Option]:
    """
    Options of a tree that stand for a stored model

    The column titles, the rules, the group headings and the fixed projects
    are all furniture the pane came with; what the tests count is what they
    put in it.
    """

    return [
        option
        for option in tree._options
        if not tree.is_static_row(option.id)
        and fixed_project_from_id(option.id or "") is None
    ]


def highlighted_index(tree: ModelTree) -> Optional[int]:
    """Index of the highlighted node among the stored rows alone"""

    if tree.highlighted is None:
        return None

    # Counted by looking the row up among the stored ones rather than by
    # subtracting what sits above it: the furniture is not all in one place,
    # since a pane can pin a block of its own below the stored rows
    highlighted = tree._options[tree.highlighted]
    options = tree_options(tree)

    if highlighted not in options:
        return None

    return options.index(highlighted)


def notification_message(app: Todooit) -> Optional[str]:
    """What the bar is saying right now, if it is saying anything"""

    if app.bar_switcher.current != "notification_bar":
        return None

    return app.bar_switcher.visible_content.message


@contextmanager
def flashed():
    """
    Every row flashed while the block runs, as (pane, row) pairs

    Read off the calls rather than off the pane: a flash fades on a timer of
    its own, so a test that looks for it afterwards is reading a race it
    sometimes loses. What is being checked is that the row was pointed out.
    """

    seen = []
    flash_row = ModelTree.flash_row

    def record(self, _id):
        seen.append((self.id, _id))
        flash_row(self, _id)

    with patch.object(ModelTree, "flash_row", record):
        yield seen
