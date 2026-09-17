"""
The move window: the project a task is filed under, retyped in one line
"""

from todooit.api import Project, Todo
from todooit.ui.screens.move import MoveScreen
from todooit.ui.screens.project_completion import build_project
from tests.test_ui.ui_base import (
    boot,
    new_project,
    new_todo,
    notification_message,
    run_pilot,
    visible_todos,
)


async def open_move(pilot) -> MoveScreen:
    await pilot.press("M")
    await pilot.pause()

    screen = pilot.app.screen
    assert isinstance(screen, MoveScreen)
    return screen


def listed(screen: MoveScreen):
    """What the list under the line is offering, as paths"""

    return ["/".join(candidate.steps) for candidate in screen._matches]


def project_named(name: str) -> Project:
    return next(p for p in Project.all() if p.description == name)


async def two_projects_and_a_task(pilot):
    """A project "inbox" with one task in it, and an empty "work" beside it"""

    await new_project(pilot, "work")
    await new_project(pilot, "inbox")
    todo = await new_todo(pilot, "file taxes")

    return todo


async def test_the_key_is_nobody_elses():
    """
    "M" is bound once and opens nothing else

    A key that is the start of a longer chord can never be pressed on its own,
    and a key already taken would quietly shadow whatever was bound first — so
    both are checked rather than assumed. Plain "m" is the pinned note and
    stays that way: the two are different keys.
    """

    async with run_pilot() as pilot:
        app = await boot(pilot)
        binds = app.api.keys.keybinds["NORMAL"]

        assert [key for key in binds if key.startswith("M")] == ["M"]
        assert binds["M"].callback == app.api.move_todo
        assert binds["m"].callback == app.api.show_pinned_note


async def test_the_window_opens_on_the_whole_tree():
    """Nothing typed yet, so every project is still an answer"""

    async with run_pilot() as pilot:
        await boot(pilot)
        await two_projects_and_a_task(pilot)

        screen = await open_move(pilot)

        assert screen.suggesting
        assert listed(screen) == ["inbox", "work"]


async def test_typing_narrows_the_list():
    async with run_pilot() as pilot:
        await boot(pilot)
        await two_projects_and_a_task(pilot)
        build_project(["work", "api"])

        screen = await open_move(pilot)
        await pilot.press(*list("ap"))

        assert listed(screen) == ["work/api"]


async def test_tab_finishes_a_name_only_one_project_answers_to():
    async with run_pilot() as pilot:
        await boot(pilot)
        await two_projects_and_a_task(pilot)

        screen = await open_move(pilot)
        await pilot.press(*list("wo"))
        await pilot.press("tab")

        # Nothing closes the name off: the whole line is the project, and
        # there is nothing after it for a space to make room for
        assert screen._input.value == "work"

        # The list stays up, down to the one project the line now names: the
        # whole line is the name, so there is nowhere else for the cursor to
        # have moved on to
        assert listed(screen) == ["work"]


async def test_tab_leaves_a_project_with_children_open():
    async with run_pilot() as pilot:
        await boot(pilot)
        await two_projects_and_a_task(pilot)
        build_project(["work", "api"])

        screen = await open_move(pilot)
        await pilot.press(*list("wo"))
        await pilot.press("tab")

        assert screen._input.value == "work/"
        assert listed(screen) == ["work/api"]


async def test_the_arrows_walk_the_matches():
    async with run_pilot() as pilot:
        await boot(pilot)
        await two_projects_and_a_task(pilot)

        screen = await open_move(pilot)

        await pilot.press("down")
        assert screen._input.value == "inbox"

        await pilot.press("down")
        assert screen._input.value == "work"

        await pilot.press("up")
        assert screen._input.value == "inbox"


async def test_a_name_with_a_space_needs_no_quotes():
    """Unlike the one line entry, where the field sits in a sentence"""

    async with run_pilot() as pilot:
        await boot(pilot)
        await two_projects_and_a_task(pilot)
        build_project(["my work"])

        screen = await open_move(pilot)
        await pilot.press(*list("my"))
        await pilot.press("tab")

        assert screen._input.value == "my work"


async def test_the_task_lands_in_the_project_that_was_picked():
    async with run_pilot() as pilot:
        app = await boot(pilot)
        todo = await two_projects_and_a_task(pilot)

        await open_move(pilot)
        await pilot.press(*list("work"))
        await pilot.press("enter")
        await pilot.pause()

        assert not isinstance(app.screen, MoveScreen)
        assert todo.parent_project == project_named("work")
        assert project_named("inbox").todos == []


async def test_the_cursor_follows_the_task_into_its_new_project():
    async with run_pilot() as pilot:
        app = await boot(pilot)
        await two_projects_and_a_task(pilot)

        await open_move(pilot)
        await pilot.press(*list("work"))
        await pilot.press("enter")
        await pilot.pause()

        tree = visible_todos(app)
        assert tree.model.uuid == project_named("work").uuid
        assert tree.current_model.description == "file taxes"
        assert app.focused is tree

        message = notification_message(app)
        assert message is not None and "work" in message


async def test_a_completed_name_is_the_project_the_task_lands_in():
    """Tab writes the path, and enter reads back exactly what it wrote"""

    async with run_pilot() as pilot:
        await boot(pilot)
        todo = await two_projects_and_a_task(pilot)
        build_project(["work", "api"])

        await open_move(pilot)
        await pilot.press(*list("ap"))
        await pilot.press("tab")
        await pilot.press("enter")
        await pilot.pause()

        assert todo.parent_project == project_named("api")


async def test_a_name_nobody_has_is_turned_down():
    async with run_pilot() as pilot:
        app = await boot(pilot)
        todo = await two_projects_and_a_task(pilot)

        screen = await open_move(pilot)
        await pilot.press(*list("nowhere"))
        await pilot.press("enter")
        await pilot.pause()

        # The window stays up with the name still in it to be corrected
        assert isinstance(app.screen, MoveScreen)
        assert screen._warning != ""
        assert screen._input.value == "nowhere"
        assert todo.parent_project == project_named("inbox")

        await pilot.press("escape")
        await pilot.pause()


async def test_a_name_two_projects_answer_to_is_turned_down():
    async with run_pilot() as pilot:
        app = await boot(pilot)
        todo = await two_projects_and_a_task(pilot)
        build_project(["work", "api"])
        build_project(["inbox", "api"])

        screen = await open_move(pilot)
        await pilot.press(*list("api"))
        await pilot.press("enter")
        await pilot.pause()

        assert isinstance(app.screen, MoveScreen)
        assert screen._warning != ""
        assert todo.parent_project == project_named("inbox")

        # Said which of them, it goes
        await pilot.press("ctrl+l")
        await pilot.press(*list("work/api"))
        await pilot.press("enter")
        await pilot.pause()

        assert not isinstance(app.screen, MoveScreen)

        # The "api" inside "work", not the one inside "inbox"
        assert todo.parent_project.description == "api"
        assert todo.parent_project.parent_project.description == "work"


async def test_the_project_it_is_already_in_is_turned_down():
    async with run_pilot() as pilot:
        app = await boot(pilot)
        todo = await two_projects_and_a_task(pilot)

        screen = await open_move(pilot)
        await pilot.press(*list("inbox"))
        await pilot.press("enter")
        await pilot.pause()

        assert isinstance(app.screen, MoveScreen)
        assert screen._warning != ""
        assert todo.parent_project == project_named("inbox")

        await pilot.press("escape")
        await pilot.pause()


async def test_an_empty_line_is_turned_down():
    async with run_pilot() as pilot:
        app = await boot(pilot)
        todo = await two_projects_and_a_task(pilot)

        screen = await open_move(pilot)
        await pilot.press("enter")
        await pilot.pause()

        assert isinstance(app.screen, MoveScreen)
        assert screen._warning != ""
        assert todo.parent_project == project_named("inbox")

        await pilot.press("escape")
        await pilot.pause()


async def test_escape_cancels_rather_than_closing_the_list():
    """The list is the whole window here, so escape is the way out of it"""

    async with run_pilot() as pilot:
        app = await boot(pilot)
        todo = await two_projects_and_a_task(pilot)

        screen = await open_move(pilot)
        assert screen.suggesting

        await pilot.press("escape")
        await pilot.pause()

        assert not isinstance(app.screen, MoveScreen)
        assert todo.parent_project == project_named("inbox")


async def test_app_keys_are_letters_here():
    """`q` toggles shading in the app; in the line it is just a letter"""

    async with run_pilot() as pilot:
        app = await boot(pilot)
        await two_projects_and_a_task(pilot)
        build_project(["quarry"])

        shading = app.api.vars.row_shading

        screen = await open_move(pilot)
        await pilot.press(*list("qu"))

        assert screen._input.value == "qu"
        assert app.api.vars.row_shading == shading

        await pilot.press("escape")
        await pilot.pause()


async def test_a_step_moved_to_a_project_stops_being_a_step():
    async with run_pilot() as pilot:
        app = await boot(pilot)
        await two_projects_and_a_task(pilot)

        # A second task, made a step of the first
        await new_todo(pilot, "find the receipts")
        await pilot.press("I")
        await pilot.pause()

        step = next(t for t in Todo.all() if t.description == "find the receipts")
        assert step.parent_todo is not None

        await open_move(pilot)
        await pilot.press(*list("work"))
        await pilot.press("enter")
        await pilot.pause()

        assert step.parent_todo is None
        assert step.parent_project == project_named("work")
        assert not isinstance(app.screen, MoveScreen)


async def test_the_key_does_nothing_over_the_projects_pane():
    """The key is the tasks pane's alone: a project is not moved this way"""

    async with run_pilot() as pilot:
        app = await boot(pilot)
        await two_projects_and_a_task(pilot)

        await pilot.press("j")  # over to the projects
        await pilot.pause()

        await pilot.press("M")
        await pilot.pause()

        assert not isinstance(app.screen, MoveScreen)


async def test_moving_from_a_pane_that_gathers_work():
    """The Today pane shows a task, and "M" moves the one under the cursor"""

    async with run_pilot() as pilot:
        app = await boot(pilot)
        await two_projects_and_a_task(pilot)

        # Due today, so the Today pane picks it up
        await pilot.press("d")
        await pilot.press(*list("today"))
        await pilot.press("enter")
        await pilot.pause()

        await pilot.press("gt")  # Today
        await pilot.pause()

        await open_move(pilot)
        await pilot.press(*list("work"))
        await pilot.press("enter")
        await pilot.pause()

        todo = next(t for t in Todo.all() if t.description == "file taxes")
        assert todo.parent_project == project_named("work")
        assert not isinstance(app.screen, MoveScreen)


async def test_picking_settles_a_name_two_projects_answer_to():
    """
    The list is the answer to its own ambiguity

    Two projects called "misc", one at the top of the tree and one inside
    another. Typing the name cannot say which — and for the one at the top
    nothing can, since it has no parent to be named after. Walking to it says
    it, and the window has nothing left to ask.
    """

    async with run_pilot() as pilot:
        app = await boot(pilot)
        todo = await two_projects_and_a_task(pilot)
        build_project(["misc"])
        build_project(["work", "misc"])

        screen = await open_move(pilot)
        await pilot.press(*list("misc"))

        assert listed(screen) == ["misc", "work/misc"]

        # The one at the top of the tree, which is written in as the same
        # bare name that was typed
        await pilot.press("down")
        assert screen._input.value == "misc"

        await pilot.press("enter")
        await pilot.pause()

        assert not isinstance(app.screen, MoveScreen)
        assert screen._warning == ""
        assert todo.parent_project.description == "misc"
        assert todo.parent_project.parent_project.is_root


async def test_picking_the_deeper_of_two_names_files_it_there():
    async with run_pilot() as pilot:
        app = await boot(pilot)
        todo = await two_projects_and_a_task(pilot)
        build_project(["misc"])
        build_project(["work", "misc"])

        screen = await open_move(pilot)
        await pilot.press(*list("misc"))

        await pilot.press("down")
        await pilot.press("down")
        assert screen._input.value == "work/misc"

        await pilot.press("enter")
        await pilot.pause()

        assert not isinstance(app.screen, MoveScreen)
        assert todo.parent_project.description == "misc"
        assert todo.parent_project.parent_project.description == "work"


async def test_a_pick_typed_over_is_no_longer_the_answer():
    """
    What was picked was an answer about the name as it stood

    Typed into again, the name is asking afresh — and a name two projects
    answer to is turned down however it was arrived at.
    """

    async with run_pilot() as pilot:
        app = await boot(pilot)
        todo = await two_projects_and_a_task(pilot)
        build_project(["misc"])
        build_project(["work", "misc"])

        screen = await open_move(pilot)
        await pilot.press(*list("misc"))
        await pilot.press("down")

        # Back to the very same name, typed rather than picked
        await pilot.press("backspace")
        await pilot.press("c")
        assert screen._input.value == "misc"

        await pilot.press("enter")
        await pilot.pause()

        assert isinstance(app.screen, MoveScreen)
        assert screen._warning != ""
        assert todo.parent_project == project_named("inbox")

        await pilot.press("escape")
        await pilot.pause()
