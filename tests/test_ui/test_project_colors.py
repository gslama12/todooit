"""
Colors a project can be given, and the "c" that means two different things
depending on which pane it is pressed over
"""

from tests.test_ui.ui_base import (
    boot,
    commit_line,
    create_and_move_to_todo,
    new_project,
    new_todo,
    run_pilot,
)
from todooit.api import Project
from todooit.api.theme import TodooitThemeBase, TokyoNight
from todooit.ui.tui import Todooit
from todooit.utils.default_config import (
    PROJECT_COLOR_NAMES,
    project_color,
    project_palette,
)


class _Api:
    """The one thing the palette asks the api for"""

    def __init__(self, theme: TodooitThemeBase):
        self.vars = type("Vars", (), {"theme": theme})()


def test_palette_has_a_color_per_digit():
    palette = project_palette(_Api(TokyoNight()))

    assert len(palette) == len(PROJECT_COLOR_NAMES) == 10
    assert len(set(palette)) == 10


def test_palette_avoids_the_signal_colors():
    """
    A project's color is a label, not a signal, so it never wears the shade
    that means "urgent" or "late" over in the tasks pane
    """

    theme = TokyoNight()
    palette = set(project_palette(_Api(theme)))

    signals = {theme.red, theme.yellow, theme.cyan, theme.green}

    assert not palette & signals


async def test_c_digit_colors_the_project():
    async with run_pilot() as pilot:
        await boot(pilot)
        project = await new_project(pilot, "painted")

        assert project.color is None

        await pilot.press("c", "4")
        await pilot.pause()

        assert project.color == 4


async def test_the_same_digit_again_takes_the_color_off():
    async with run_pilot() as pilot:
        await boot(pilot)
        project = await new_project(pilot, "painted")

        await pilot.press("c", "7")
        await pilot.pause()
        assert project.color == 7

        await pilot.press("c", "7")
        await pilot.pause()
        assert project.color is None


async def test_another_digit_repaints_rather_than_clearing():
    async with run_pilot() as pilot:
        await boot(pilot)
        project = await new_project(pilot, "painted")

        await pilot.press("c", "2")
        await pilot.pause()
        await pilot.press("c", "9")
        await pilot.pause()

        assert project.color == 9


async def test_every_digit_lands_in_its_own_slot():
    async with run_pilot() as pilot:
        await boot(pilot)
        project = await new_project(pilot, "painted")

        for slot in range(len(PROJECT_COLOR_NAMES)):
            await pilot.press("c", str(slot))
            await pilot.pause()
            assert project.color == slot

            # off again, so the next digit is painting a blank project
            await pilot.press("c", str(slot))
            await pilot.pause()


async def test_c_still_ticks_a_todo_off_over_the_tasks_pane():
    """
    The color chords open with the same key that completes a todo, so the
    binding is the projects pane's alone: over the tasks it is still one key
    """

    async with run_pilot() as pilot:
        await create_and_move_to_todo(pilot)
        todo = await new_todo(pilot, "ship it")

        assert todo.pending

        await pilot.press("c")
        await pilot.pause()

        assert not todo.pending


async def test_c_over_the_projects_does_not_reach_the_todos():
    """
    The digit is what finishes the chord: "c" on its own over the projects
    waits, and nothing at all is ticked off in the pane beside it
    """

    async with run_pilot() as pilot:
        await create_and_move_to_todo(pilot)
        todo = await new_todo(pilot, "ship it")

        app = pilot.app
        assert isinstance(app, Todooit)

        await pilot.press("j")
        await pilot.pause()

        await pilot.press("c")
        await pilot.pause()

        assert todo.pending
        assert app.project_tree.current_model.color is None

        # and the waiting chord is still waiting: the digit finishes it
        await pilot.press("3")
        await pilot.pause()

        assert app.project_tree.current_model.color == 3
        assert todo.pending


async def test_the_color_survives_a_restart():
    async with run_pilot() as pilot:
        await boot(pilot)
        project = await new_project(pilot, "painted")

        await pilot.press("c", "5")
        await pilot.pause()

        stored = Project.from_id(str(project.id))
        assert stored.color == 5


async def test_an_uncolored_project_asks_the_palette_for_nothing():
    api = _Api(TokyoNight())

    class Plain:
        color = None

    class Fixed:
        """A fixed project has no slot to be in at all"""

    assert project_color(Plain(), api) is None
    assert project_color(Fixed(), api) is None


def test_a_slot_outside_the_palette_reads_as_no_color():
    """
    A database written by a later version with a longer palette still opens
    """

    api = _Api(TokyoNight())

    class Stray:
        color = 99

    assert project_color(Stray(), api) is None


async def test_the_digit_colors_the_sub_projects_too():
    """
    The color is the tree's and not the row's: everything filed under the
    project the digit was typed over is repainted with it
    """

    async with run_pilot() as pilot:
        await boot(pilot)
        project = await new_project(pilot, "painted")

        child = project.add_project()
        child.description = "under it"
        child.save()

        grandchild = child.add_project()
        grandchild.description = "further under it"
        grandchild.save()

        await pilot.press("c", "4")
        await pilot.pause()

        assert [p.color for p in (project, child, grandchild)] == [4, 4, 4]


async def test_the_digit_over_a_sub_project_colors_the_whole_tree():
    """
    A sub project has no color of its own to paint, so the digit typed over
    one reaches the project at the top of the tree it is in
    """

    async with run_pilot() as pilot:
        app = await boot(pilot)
        project = await new_project(pilot, "painted")

        # N opens a sub project under the highlighted one, which the cursor
        # then sits on: the digit below is typed over the child, not the top
        await pilot.press("N")
        await commit_line(pilot, "under it")

        child = app.project_tree.current_model
        assert isinstance(child, Project)
        assert child.parent_project is project

        await pilot.press("c", "6")
        await pilot.pause()

        assert child.color == 6
        assert project.color == 6

        # and the same digit again clears the tree from down here as well
        await pilot.press("c", "6")
        await pilot.pause()

        assert child.color is None
        assert project.color is None


async def test_a_sub_project_made_after_the_color_arrives_wearing_it():
    async with run_pilot() as pilot:
        app = await boot(pilot)
        await new_project(pilot, "painted")

        await pilot.press("c", "8")
        await pilot.pause()

        await pilot.press("N")
        await commit_line(pilot, "under it")

        child = app.project_tree.current_model
        assert isinstance(child, Project)

        assert child.color == 8
