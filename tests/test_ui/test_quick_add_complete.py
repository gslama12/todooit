"""
The quick add line completing a `#project` the way a shell completes a path
"""

from tests.test_ui.test_quick_add_ui import open_quick_add
from tests.test_ui.ui_base import boot, new_project, run_pilot
from todooit.api import Todo
from todooit.ui.screens.project_completion import build_project
from todooit.ui.screens.quick_add import QuickAddScreen


def tree(*paths: str) -> None:
    """
    Builds the projects a test needs, written as the paths they sit at
    """

    for path in paths:
        build_project(path.split("/"))


def listed(screen: QuickAddScreen):
    """What the list under the line is offering, as paths"""

    return ["/".join(candidate.steps) for candidate in screen._matches]


async def test_the_marker_offers_every_project():
    async with run_pilot() as pilot:
        await boot(pilot)
        await new_project(pilot, "inbox")
        tree("work/api", "home")

        screen = await open_quick_add(pilot)
        await pilot.press(*list("buy milk #"))

        assert screen.suggesting
        assert listed(screen) == ["home", "inbox", "work", "work/api"]


async def test_typing_narrows_the_list():
    async with run_pilot() as pilot:
        await boot(pilot)
        await new_project(pilot, "inbox")
        tree("work/api", "home/api")

        screen = await open_quick_add(pilot)
        await pilot.press(*list("buy milk #ap"))

        assert listed(screen) == ["home/api", "work/api"]


async def test_the_list_is_only_up_while_the_cursor_is_in_the_name():
    async with run_pilot() as pilot:
        await boot(pilot)
        await new_project(pilot, "inbox")

        screen = await open_quick_add(pilot)
        await pilot.press(*list("#inbox"))
        assert screen.suggesting

        # A space ends the field, and the rest of the line is the task
        await pilot.press("space")
        assert not screen.suggesting


async def test_tab_finishes_a_name_only_one_project_answers_to():
    async with run_pilot() as pilot:
        await boot(pilot)
        await new_project(pilot, "inbox")

        screen = await open_quick_add(pilot)
        await pilot.press(*list("buy milk #inb"))
        await pilot.press("tab")

        # Finished off with a space, since there is nothing inside it: the
        # field is done and the description carries on after it
        assert screen._input.value == "buy milk #inbox "
        assert not screen.suggesting


async def test_tab_leaves_a_project_with_children_open():
    async with run_pilot() as pilot:
        await boot(pilot)
        await new_project(pilot, "inbox")
        tree("work/api", "work/web")

        screen = await open_quick_add(pilot)
        await pilot.press(*list("#wo"))
        await pilot.press("tab")

        assert screen._input.value == "#work/"
        # And the list has turned into what is inside it
        assert listed(screen) == ["work/api", "work/web"]


async def test_tab_grows_the_name_as_far_as_the_matches_agree():
    async with run_pilot() as pilot:
        await boot(pilot)
        await new_project(pilot, "inbox")
        tree("deploy", "delete")

        screen = await open_quick_add(pilot)
        await pilot.press(*list("#d"))
        await pilot.press("tab")

        # As much as both agree on, and no further: the two are still up
        assert screen._input.value == "#de"
        assert listed(screen) == ["delete", "deploy"]


async def test_tab_walks_the_matches_once_they_stop_agreeing():
    async with run_pilot() as pilot:
        await boot(pilot)
        await new_project(pilot, "inbox")
        tree("work/api", "home/api")

        screen = await open_quick_add(pilot)
        await pilot.press(*list("#api"))

        await pilot.press("tab")
        assert screen._input.value == "#home/api"

        await pilot.press("tab")
        assert screen._input.value == "#work/api"

        # Round rather than stopped at the end, the way the finder walks
        await pilot.press("tab")
        assert screen._input.value == "#home/api"

        await pilot.press("shift+tab")
        assert screen._input.value == "#work/api"


async def test_the_arrows_walk_the_matches_too():
    async with run_pilot() as pilot:
        await boot(pilot)
        await new_project(pilot, "inbox")
        tree("work/api", "home/api")

        screen = await open_quick_add(pilot)
        await pilot.press(*list("#api"))

        await pilot.press("down")
        assert screen._input.value == "#home/api"
        assert screen._index == 0

        await pilot.press("up")
        assert screen._input.value == "#work/api"
        assert screen._index == 1


async def test_a_completion_says_only_as_much_as_it_has_to():
    async with run_pilot() as pilot:
        await boot(pilot)
        await new_project(pilot, "inbox")
        tree("work/api", "work/web")

        screen = await open_quick_add(pilot)
        await pilot.press(*list("#we"))
        await pilot.press("tab")

        # `web` is enough -- nothing else is called it -- so the parent it
        # sits under is not spelled out
        assert screen._input.value == "#web "


async def test_a_name_with_a_space_is_completed_inside_quotes():
    async with run_pilot() as pilot:
        await boot(pilot)
        await new_project(pilot, "inbox")
        tree("my house")

        screen = await open_quick_add(pilot)
        await pilot.press(*list("buy a lamp #my"))
        await pilot.press("tab")

        assert screen._input.value == 'buy a lamp #"my house" '

        await pilot.press("enter")
        await pilot.pause()

        (todo,) = Todo.all()
        assert todo.description == "buy a lamp"
        assert todo.parent_project.description == "my house"


async def test_a_completed_project_is_the_one_the_task_lands_in():
    async with run_pilot() as pilot:
        await boot(pilot)
        await new_project(pilot, "inbox")
        tree("work/api")

        screen = await open_quick_add(pilot)
        await pilot.press(*list("ship it #ap"))
        await pilot.press("tab")
        assert screen._input.value == "ship it #api "

        await pilot.press("enter")
        await pilot.pause()

        (todo,) = Todo.all()
        assert todo.description == "ship it"
        assert todo.parent_project.description == "api"
        assert todo.parent_project.parent_project.description == "work"


async def test_descending_into_a_project_and_finishing_there():
    async with run_pilot() as pilot:
        await boot(pilot)
        await new_project(pilot, "inbox")
        tree("work/api", "work/web")

        screen = await open_quick_add(pilot)
        await pilot.press(*list("ship it #w"))

        # `work` first, left open because there is something inside it
        await pilot.press("tab")
        assert screen._input.value == "ship it #work/"

        # then the one thing inside it that starts with an `a`
        await pilot.press("a", "tab")
        assert screen._input.value == "ship it #work/api "

        await pilot.press("enter")
        await pilot.pause()

        (todo,) = Todo.all()
        assert todo.parent_project.description == "api"


async def test_escape_puts_the_list_away_before_it_leaves():
    async with run_pilot() as pilot:
        app = await boot(pilot)
        await new_project(pilot, "inbox")

        screen = await open_quick_add(pilot)
        await pilot.press(*list("buy milk #i"))
        assert screen.suggesting

        # The first escape is about the list, which is what is in the way
        await pilot.press("escape")
        await pilot.pause()
        assert isinstance(app.screen, QuickAddScreen)
        assert not screen.suggesting
        assert screen._input.value == "buy milk #i"

        # The second is about the line
        await pilot.press("escape")
        await pilot.pause()
        assert not isinstance(app.screen, QuickAddScreen)


async def test_typing_brings_a_dismissed_list_back():
    async with run_pilot() as pilot:
        await boot(pilot)
        await new_project(pilot, "inbox")

        screen = await open_quick_add(pilot)
        await pilot.press(*list("#i"))
        await pilot.press("escape")
        assert not screen.suggesting

        await pilot.press("n")
        assert screen.suggesting


async def test_a_name_nobody_has_offers_nothing():
    async with run_pilot() as pilot:
        await boot(pilot)
        await new_project(pilot, "inbox")

        screen = await open_quick_add(pilot)
        await pilot.press(*list("buy milk #zzz"))

        assert not screen.suggesting
        assert listed(screen) == []


async def test_tab_with_nothing_to_complete_does_nothing_at_all():
    async with run_pilot() as pilot:
        await boot(pilot)
        await new_project(pilot, "inbox")

        screen = await open_quick_add(pilot)
        await pilot.press(*list("buy milk"))
        assert not screen.suggesting

        # Not even a tab character: it cannot be seen in the line it lands
        # in, and would ride along into the description of the task
        await pilot.press("tab")
        assert screen._input.value == "buy milk"

        await pilot.press(*list(" #zzz"), "tab", "shift+tab")
        assert screen._input.value == "buy milk #zzz"


async def test_a_completed_line_still_reads_back_as_the_task_it_says():
    async with run_pilot() as pilot:
        await boot(pilot)
        await new_project(pilot, "inbox")
        tree("work/api")

        screen = await open_quick_add(pilot)
        await pilot.press(*list("ship it #ap"))
        await pilot.press("tab")
        await pilot.press(*list("p1 tomorrow"))

        assert screen._input.value == "ship it #api p1 tomorrow"

        await pilot.press("enter")
        await pilot.pause()

        (todo,) = Todo.all()
        assert todo.description == "ship it"
        assert todo.priority == 1
        assert todo.scheduled is not None
        assert todo.parent_project.description == "api"


async def test_a_picked_project_is_the_one_the_task_lands_in():
    """
    Two projects called "misc", and the pick stands while the line goes on

    The one at the top of the tree cannot be named by a path — there is no
    parent to name it after — so picking it out of the list is the only way
    to say it, and the rest of the sentence must not undo that.
    """

    async with run_pilot() as pilot:
        await boot(pilot)
        await new_project(pilot, "inbox")
        tree("misc", "work/misc")

        screen = await open_quick_add(pilot)
        await pilot.press(*list("buy milk #misc"))

        assert listed(screen) == ["misc", "work/misc"]

        # The one at the top of the tree, and then the rest of the line
        await pilot.press("down")
        assert screen._input.value == "buy milk #misc"

        await pilot.press(*list(" p1"))
        await pilot.press("enter")
        await pilot.pause()

        (todo,) = Todo.all()
        assert todo.description == "buy milk"
        assert todo.parent_project.description == "misc"
        assert todo.parent_project.parent_project.is_root
