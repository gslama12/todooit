"""
`t` ("to"): flash mode, a label on every row on screen and a jump to the one typed
"""

from typing import List

from tests.test_ui.ui_base import (
    boot,
    descriptions,
    new_project,
    new_todo,
    run_pilot,
    visible_todos,
)
from todooit.api import Project
from todooit.ui.tui import Todooit
from todooit.ui.widgets.trees import TodosTree
from todooit.ui.widgets.trees.flash_jump import FLASH_ALPHABET, flash_labels


def test_labels_are_single_keys_while_the_alphabet_lasts():
    assert flash_labels(3) == ["a", "s", "d"]
    assert flash_labels(len(FLASH_ALPHABET)) == list(FLASH_ALPHABET)


def test_labels_are_all_pairs_once_it_runs_out():
    labels = flash_labels(len(FLASH_ALPHABET) + 1)

    assert all(len(label) == 2 for label in labels)
    assert labels[:3] == ["aa", "as", "ad"]
    assert len(set(labels)) == len(labels)


async def project_with(pilot, count: int) -> TodosTree:
    """A project holding `count` tasks, its pane in front and focused"""

    app = pilot.app
    assert isinstance(app, Todooit)

    await new_project(pilot, "home")
    project = app.project_tree.current_model
    assert isinstance(project, Project)

    for n in range(count):
        todo = project.add_todo()
        todo.description = f"task {n:02}"
        todo.save()

    await pilot.press("ö")
    await pilot.pause()

    tree = visible_todos(app)
    tree.force_refresh()
    await pilot.pause()

    return tree


def labelled_rows(tree: TodosTree) -> List[str]:
    """What the rows the labels point at say, in label order"""

    ids = [tree._options[index].id for index in tree._flash_labels.values()]
    return [tree._renderers[_id].model.description for _id in ids if _id]


async def test_typing_a_label_puts_the_cursor_on_its_row():
    async with run_pilot() as pilot:
        app = await boot(pilot)
        tree = await project_with(pilot, 5)
        assert tree.current_model.description == "task 00"

        await pilot.press("t")
        await pilot.pause()

        assert app.todooit_mode == "FLASH"
        assert list(tree._flash_labels) == ["a", "s", "d", "f", "g"]
        assert labelled_rows(tree) == descriptions(tree)

        await pilot.press("d")
        await pilot.pause()

        assert tree.current_model.description == "task 02"
        assert not tree.is_flashing
        assert app.todooit_mode == "NORMAL"
        assert app.focused is tree


async def test_a_jump_in_the_projects_pane_opens_that_project():
    async with run_pilot() as pilot:
        app = await boot(pilot)

        home = await new_project(pilot, "home")
        await new_todo(pilot, "water plants")
        work = await new_project(pilot, "work")

        projects = app.project_tree
        assert app.focused is projects
        assert projects.current_model is work

        await pilot.press("t")
        await pilot.pause()

        home_label = next(
            label
            for label, index in projects._flash_labels.items()
            if projects._options[index].id == home.uuid
        )

        await pilot.press(*home_label)
        await pilot.pause()

        assert projects.current_model.description == "home"
        assert app.focused is projects
        assert descriptions(visible_todos(app)) == ["water plants"]


async def test_escape_takes_the_labels_down_where_the_cursor_was():
    async with run_pilot() as pilot:
        app = await boot(pilot)
        tree = await project_with(pilot, 3)

        await pilot.press("l", "t", "escape")
        await pilot.pause()

        assert not tree.is_flashing
        assert app.todooit_mode == "NORMAL"
        assert tree.current_model.description == "task 01"


async def test_a_key_that_is_no_label_cancels_and_is_used_up():
    async with run_pilot() as pilot:
        app = await boot(pilot)
        tree = await project_with(pilot, 3)

        # `n` would start a new task; here it is only the way out
        await pilot.press("t", "n")
        await pilot.pause()

        assert not tree.is_flashing
        assert not tree.is_editing
        assert app.todooit_mode == "NORMAL"
        assert descriptions(tree) == ["task 00", "task 01", "task 02"]


async def test_pairs_wait_for_the_second_key_and_backspace_takes_the_first_back():
    async with run_pilot() as pilot:
        app = await boot(pilot)
        tree = await project_with(pilot, 40)

        await pilot.press("t")
        await pilot.pause()

        rows = len(tree._flash_labels)
        assert rows > len(FLASH_ALPHABET), "the pane needs more rows than letters"
        assert all(len(label) == 2 for label in tree._flash_labels)

        await pilot.press("s")
        await pilot.pause()
        assert tree.is_flashing
        assert tree._flash_typed == "s"

        await pilot.press("backspace", "a", "d")
        await pilot.pause()

        assert not tree.is_flashing
        assert tree.current_model.description == "task 02"
        assert app.todooit_mode == "NORMAL"


async def test_a_pair_with_a_wrong_second_key_cancels():
    async with run_pilot() as pilot:
        await boot(pilot)
        tree = await project_with(pilot, 40)

        await pilot.press("t", "a", "1")
        await pilot.pause()

        assert not tree.is_flashing
        assert tree.current_model.description == "task 00"


async def test_only_rows_on_screen_get_a_label():
    async with run_pilot() as pilot:
        await boot(pilot)
        tree = await project_with(pilot, 80)

        await pilot.press("G")
        await pilot.pause()

        await pilot.press("t")
        await pilot.pause()

        labelled = labelled_rows(tree)
        assert 0 < len(labelled) < 80
        assert "task 79" in labelled
        assert "task 00" not in labelled


async def test_an_empty_pane_stays_in_normal_mode():
    async with run_pilot() as pilot:
        app = await boot(pilot)
        await new_project(pilot, "empty")
        await pilot.press("ö")
        await pilot.pause()

        tree = visible_todos(app)
        await pilot.press("t")
        await pilot.pause()

        assert not tree.is_flashing
        assert app.todooit_mode == "NORMAL"


async def test_a_single_row_still_gets_its_label():
    async with run_pilot() as pilot:
        app = await boot(pilot)
        tree = await project_with(pilot, 1)

        await pilot.press("t")
        await pilot.pause()

        assert list(tree._flash_labels) == ["a"]
        assert app.todooit_mode == "FLASH"


async def test_the_pane_being_rebuilt_cancels():
    async with run_pilot() as pilot:
        app = await boot(pilot)
        tree = await project_with(pilot, 3)

        await pilot.press("t")
        await pilot.pause()

        tree.force_refresh()
        await pilot.pause()

        assert not tree.is_flashing
        assert app.todooit_mode == "NORMAL"


async def test_the_label_is_drawn_over_the_left_edge_of_its_row():
    async with run_pilot() as pilot:
        await boot(pilot)
        tree = await project_with(pilot, 3)

        index = tree.get_option_index(tree.current_model.uuid)
        y = tree._index_to_line[index] - tree.scroll_offset.y
        before = tree.render_line(y).text

        await pilot.press("t")
        await pilot.pause()

        after = tree.render_line(y).text

        # Covered, not pushed along: the row keeps its width and the rest of its text
        assert after.startswith("a")
        assert len(after) == len(before)
        assert after[1:] == before[1:]

