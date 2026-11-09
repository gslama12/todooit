"""
`f` ("flash"): flash mode, a label on every row on screen and a jump to the one typed
"""

from typing import List, Tuple

from rich.segment import Segment
from textual.strip import Strip

from tests.test_ui.ui_base import (
    boot,
    descriptions,
    new_project,
    new_todo,
    run_pilot,
    visible_todos,
)
from todooit.api import Project, Todo
from todooit.api.expansion import set_expanded
from todooit.ui.tui import Todooit
from todooit.ui.widgets.renderers import COLUMN_PADDING
from todooit.ui.widgets.trees import TodosTree
from todooit.ui.widgets.trees.flash_jump import FLASH_ALPHABET, flash_labels
from todooit.ui.widgets.trees.model_tree import ModelTree


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

        await pilot.press("f")
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

        await pilot.press("f")
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

        await pilot.press("l", "f", "escape")
        await pilot.pause()

        assert not tree.is_flashing
        assert app.todooit_mode == "NORMAL"
        assert tree.current_model.description == "task 01"


async def test_a_key_that_is_no_label_cancels_and_is_used_up():
    async with run_pilot() as pilot:
        app = await boot(pilot)
        tree = await project_with(pilot, 3)

        # `n` would start a new task; here it is only the way out
        await pilot.press("f", "n")
        await pilot.pause()

        assert not tree.is_flashing
        assert not tree.is_editing
        assert app.todooit_mode == "NORMAL"
        assert descriptions(tree) == ["task 00", "task 01", "task 02"]


async def test_pairs_wait_for_the_second_key_and_backspace_takes_the_first_back():
    async with run_pilot() as pilot:
        app = await boot(pilot)
        tree = await project_with(pilot, 40)

        await pilot.press("f")
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

        await pilot.press("f", "a", "1")
        await pilot.pause()

        assert not tree.is_flashing
        assert tree.current_model.description == "task 00"


async def test_only_rows_on_screen_get_a_label():
    async with run_pilot() as pilot:
        await boot(pilot)
        tree = await project_with(pilot, 80)

        await pilot.press("G")
        await pilot.pause()

        await pilot.press("f")
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
        await pilot.press("f")
        await pilot.pause()

        assert not tree.is_flashing
        assert app.todooit_mode == "NORMAL"


async def test_a_single_row_still_gets_its_label():
    async with run_pilot() as pilot:
        app = await boot(pilot)
        tree = await project_with(pilot, 1)

        await pilot.press("f")
        await pilot.pause()

        assert list(tree._flash_labels) == ["a"]
        assert app.todooit_mode == "FLASH"


async def test_the_pane_being_rebuilt_cancels():
    async with run_pilot() as pilot:
        app = await boot(pilot)
        tree = await project_with(pilot, 3)

        await pilot.press("f")
        await pilot.pause()

        tree.force_refresh()
        await pilot.pause()

        assert not tree.is_flashing
        assert app.todooit_mode == "NORMAL"


def row_line(tree: ModelTree, uuid: str) -> int:
    """The line of the pane a row starts on"""

    index = tree.get_option_index(uuid)
    return tree._index_to_line[index] - tree.scroll_offset.y


async def test_the_label_is_drawn_over_the_checkbox_of_a_top_level_row():
    async with run_pilot() as pilot:
        await boot(pilot)
        tree = await project_with(pilot, 3)

        y = row_line(tree, tree.current_model.uuid)
        before = tree.render_line(y).text

        await pilot.press("f")
        await pilot.pause()

        after = tree.render_line(y).text

        # Covered, not pushed along: the row keeps its width and the rest of its text
        assert after[COLUMN_PADDING] == "a"
        assert len(after) == len(before)
        assert after[:COLUMN_PADDING] == before[:COLUMN_PADDING]
        assert after[COLUMN_PADDING + 1 :] == before[COLUMN_PADDING + 1 :]


async def nested(pilot) -> Tuple[TodosTree, Todo, Todo]:
    """A task two levels below a top-level one, all expanded, and the tree drawing them"""

    tree = await project_with(pilot, 1)
    top = tree.current_model
    assert isinstance(top, Todo)
    middle = top.add_todo()
    middle.description = "step"
    middle.save()
    bottom = middle.add_todo()
    bottom.description = "sub-step"
    bottom.save()

    set_expanded(top.uuid, True)
    set_expanded(middle.uuid, True)

    # Recorded now, or the next key press would and redraw under the labels
    tree.api.history.record()
    tree.force_refresh()
    await pilot.pause()

    return tree, middle, bottom


async def test_the_label_of_an_indented_row_follows_its_indent():
    async with run_pilot() as pilot:
        await boot(pilot)
        tree, middle, bottom = await nested(pilot)

        rows = [(middle, "s", 4), (bottom, "d", 8)]
        before = [tree.render_line(row_line(tree, todo.uuid)).text for todo, _, _ in rows]

        await pilot.press("f")
        await pilot.pause()

        for (todo, label, guide_width), was in zip(rows, before):
            after = tree.render_line(row_line(tree, todo.uuid)).text
            column = COLUMN_PADDING + guide_width

            assert after[column] == label
            # The guides are left standing, and only the checkbox is covered
            assert after[:column] == was[:column]
            assert after[column + 1 :] == was[column + 1 :]


async def test_a_pair_on_an_indented_row_stays_together():
    async with run_pilot() as pilot:
        await boot(pilot)
        tree, _, bottom = await nested(pilot)

        tree._flash_labels = {"ab": tree.get_option_index(bottom.uuid)}
        tree.refresh()
        await pilot.pause()

        column = COLUMN_PADDING + 8
        after = tree.render_line(row_line(tree, bottom.uuid)).text

        assert after[column : column + 2] == "ab"


async def test_the_label_of_a_project_row_follows_its_indent():
    async with run_pilot() as pilot:
        app = await boot(pilot)

        parent = await new_project(pilot, "parent")
        child = parent.add_project()
        child.description = "child"
        child.save()
        set_expanded(parent.uuid, True)

        projects = app.project_tree
        projects.api.history.record()
        projects.force_refresh()
        await pilot.pause()

        await pilot.press("f")
        await pilot.pause()

        label = next(
            label
            for label, index in projects._flash_labels.items()
            if projects._options[index].id == child.uuid
        )
        line = row_line(projects, child.uuid)

        assert projects.render_line(line).text[COLUMN_PADDING + 4] == label


async def test_a_pane_too_narrow_for_the_indent_still_shows_the_whole_label():
    async with run_pilot() as pilot:
        await boot(pilot)
        tree = await project_with(pilot, 1)

        strip = Strip([Segment("0123456789")], 10)

        assert tree._flash_strip(strip, "ab", 100).text == "01234567ab"
