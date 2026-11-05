"""
The projects pane: stored projects among the fixed ones
"""

from tests.test_ui.ui_base import (
    boot,
    commit_line,
    highlighted_index,
    new_project,
    notification_message,
    run_pilot,
    set_clipboard,
    tree_options,
    visible_todos,
)
from todooit.api import BIN, TODAY, Project, Todo
from todooit.ui.tui import Todooit
from todooit.ui.widgets.trees.projects_tree import ProjectsTree


def shown(tree) -> list:
    return [option.id for option in tree_options(tree)]


async def test_projects_tree_basics():
    async with run_pilot() as pilot:
        app = await boot(pilot)
        ptree = app.project_tree

        assert len(tree_options(ptree)) == 0

        # Direct model additions draw a row each
        ptree.add_project()
        ptree.add_project()
        ptree.add_project()
        p = ptree.add_project()

        assert len(tree_options(ptree)) == 4

        # Highlighting a project brings its pane to the front
        ptree.highlight_id(p)
        await pilot.pause()

        assert highlighted_index(ptree) == 3
        assert visible_todos(app).model.uuid == p

        # Child nodes hide and show with their parent's expansion
        child = ptree.current_model.add_project()
        child.description = "child"
        child.save()
        ptree.force_refresh()

        assert len(tree_options(ptree)) == 5  # expanded by default

        ptree.toggle_expand()
        assert len(tree_options(ptree)) == 4

        ptree.toggle_expand()
        assert len(tree_options(ptree)) == 5


async def test_sub_project_count_shows_only_while_collapsed():
    """
    An open project has its sub projects on the rows below it, so the count
    trailing its name is only drawn once it is folded shut
    """

    async with run_pilot() as pilot:
        app = await boot(pilot)
        ptree = app.project_tree

        outer = await new_project(pilot, "outer")
        inner = outer.add_project()
        inner.description = "inner"
        inner.save()
        ptree.force_refresh()
        ptree.highlight_id(outer.uuid)
        await pilot.pause()

        def drawn() -> str:
            return ptree.formatter.description.format_value("outer", outer).plain

        assert "(1)" not in drawn()

        ptree.toggle_expand()
        assert drawn().endswith("outer (1)")

        ptree.toggle_expand()
        assert "(1)" not in drawn()


async def test_add_and_commit_with_enter():
    async with run_pilot() as pilot:
        app = await boot(pilot)
        ptree = app.project_tree

        await pilot.press("j", "n")
        await commit_line(pilot, "first")

        assert [p.description for p in Project.all()] == ["first"]
        assert highlighted_index(ptree) == 0

        await pilot.press("n")
        await commit_line(pilot, "second")

        assert len(tree_options(ptree)) == 2
        assert highlighted_index(ptree) == 1


async def test_escape_discards_a_new_project():
    """A project left without a name is nothing to keep"""

    async with run_pilot() as pilot:
        app = await boot(pilot)
        ptree = app.project_tree

        await pilot.press("j", "n")
        await pilot.press(*list("never kept"))
        await pilot.press("escape")
        await pilot.pause()

        assert Project.all() == []
        assert tree_options(ptree) == []


async def _discard_then_add_again(pilot, key: str) -> Project:
    """
    Adds a project with `key`, escapes it unnamed, adds one again from the
    same row and opens its tasks pane. The second add reuses the discarded
    row's id.
    """

    app = pilot.app
    ptree = app.project_tree
    start = ptree.current_model.uuid

    await pilot.press(key, *list("never kept"))
    discarded = ptree.current_model.id
    await pilot.press("escape")
    await pilot.pause()

    ptree.highlight_id(start)
    await pilot.press(key)
    await commit_line(pilot, "kept")

    project = app.project_tree.current_model
    assert project.id == discarded

    await pilot.press("ö")
    await pilot.pause()

    assert visible_todos(app).model is project
    return project


async def test_escaped_project_leaves_no_pane_behind():
    """The next project reusing the escaped one's id gets a pane of its own"""

    async with run_pilot() as pilot:
        await boot(pilot)
        await pilot.press("j")

        project = await _discard_then_add_again(pilot, "n")

        await pilot.press("n")
        await commit_line(pilot, "task")

        assert [t.description for t in project.todos] == ["task"]


async def test_escaped_sub_project_leaves_no_pane_behind():
    async with run_pilot() as pilot:
        await boot(pilot)
        outer = await new_project(pilot, "outer")

        inner = await _discard_then_add_again(pilot, "N")
        assert inner.parent_project == outer

        await pilot.press("n")
        await commit_line(pilot, "task")

        assert [t.description for t in inner.todos] == ["task"]


async def test_blank_name_is_dropped_even_on_enter():
    async with run_pilot() as pilot:
        await boot(pilot)

        await pilot.press("j", "n")
        await commit_line(pilot, "   ")

        assert Project.all() == []


async def test_renaming_a_project():
    async with run_pilot() as pilot:
        await boot(pilot)
        await new_project(pilot, "old name")

        await pilot.press("i")
        # A fresh edit starts with the old name in the buffer; wipe it
        await pilot.press("ctrl+l")
        await commit_line(pilot, "new name")

        assert [p.description for p in Project.all()] == ["new name"]


async def test_nested_project_via_child_key():
    async with run_pilot() as pilot:
        app = await boot(pilot)
        ptree = app.project_tree

        outer = await new_project(pilot, "outer")

        await pilot.press("N")
        await commit_line(pilot, "inner")

        inner = next(p for p in Project.all() if p.description == "inner")
        assert inner.parent_project == outer

        # The parent was expanded to show it, and the cursor is on it
        assert len(tree_options(ptree)) == 2
        assert ptree.current_model.uuid == inner.uuid

        # `h` folds the parent away again
        await pilot.press("k")  # up to the parent
        await pilot.press("h")
        await pilot.pause()

        assert len(tree_options(ptree)) == 1


async def test_empty_bin_notifies_when_empty():
    async with run_pilot() as pilot:
        app = await boot(pilot)

        await pilot.press("g", "b")
        await pilot.pause()
        await pilot.press("Y", "Y")
        await pilot.pause()

        assert notification_message(app) == "The Bin is already empty"


async def test_empty_completed_notifies_when_empty():
    async with run_pilot() as pilot:
        app = await boot(pilot)

        await pilot.press("g", "c")
        await pilot.pause()
        await pilot.press("Y", "Y")
        await pilot.pause()

        assert notification_message(app) == "Completed is already empty"


async def test_fixed_projects_cannot_be_edited():
    async with run_pilot() as pilot:
        app = await boot(pilot)
        ptree = app.project_tree

        # The keys act on the focused pane, so the projects pane first;
        # its cursor starts on Today, a fixed project
        await pilot.press("j")
        assert ptree.current_model is TODAY

        for key in ("i",):
            await pilot.press(key)
            await pilot.pause()
            assert not ptree.is_editing

        message = notification_message(app)
        assert message is not None and "fixed project" in message

        # Deleting is refused the same way, without a confirm
        await pilot.press("y", "y")
        await pilot.pause()
        assert app.bar_switcher.current != "confirm_bar"

        # Shifting is refused too
        await pilot.press("K")
        await pilot.press("L")
        await pilot.pause()
        assert ptree.current_model is TODAY


async def test_adding_from_a_fixed_row_starts_the_stored_block():
    """`n` on Today has no sibling to add beside; it starts the tree"""

    async with run_pilot() as pilot:
        app = await boot(pilot)
        ptree = app.project_tree

        assert ptree.current_model is TODAY

        await pilot.press("j", "n")
        await commit_line(pilot, "first real project")

        project = Project.all()[0]
        assert project.description == "first real project"
        assert project.parent_project is not None
        assert project.parent_project.is_root


async def test_project_remove_cancelled():
    async with run_pilot() as pilot:
        app = await boot(pilot)
        ptree = app.project_tree

        await new_project(pilot, "keep me")
        p1 = ptree.current_model

        await pilot.press("y", "y")
        await pilot.pause()
        await pilot.press("n")
        await pilot.pause()

        assert [p.description for p in Project.all()] == ["keep me"]
        assert visible_todos(app).model.uuid == p1.uuid


async def test_project_delete_for_good():
    async with run_pilot() as pilot:
        await boot(pilot)

        await new_project(pilot, "doomed")

        await pilot.press("y", "y")
        await pilot.pause()
        await pilot.press("y")
        await pilot.pause()

        assert Project.all() == []


async def test_project_to_bin_keeps_its_work():
    """`xx` on a project throws only the row away; the work lands in the Bin"""

    async with run_pilot() as pilot:
        await boot(pilot)

        await new_project(pilot, "dropped")
        await pilot.press("ö", "n")
        await commit_line(pilot, "orphaned work")

        await pilot.press("j")
        await pilot.press("x", "x")
        await pilot.pause()

        assert Project.all() == []

        todo = Todo.all()[0]
        assert todo.is_binned
        assert todo.origin_path == "dropped"
        assert BIN.todos == [todo]


async def test_shifts():
    async with run_pilot() as pilot:
        app = await boot(pilot)
        ptree = app.project_tree

        await new_project(pilot, "one")
        await pilot.press("n")
        await commit_line(pilot, "two")

        assert highlighted_index(ptree) == 1

        # Shift the highlighted project up, then against the edges.
        # `Project.all()` comes back in insertion order, so the filing has to
        # be read off order_index the way the pane reads it.
        await pilot.press("K")
        await pilot.pause()
        assert highlighted_index(ptree) == 0
        filed = sorted(Project.all(), key=lambda p: p.order_index)
        assert [p.description for p in filed] == ["two", "one"]

        await pilot.press("K")
        await pilot.pause()
        assert highlighted_index(ptree) == 0

        await pilot.press("L")
        await pilot.pause()
        assert highlighted_index(ptree) == 1

        await pilot.press("L")
        await pilot.pause()
        assert highlighted_index(ptree) == 1


async def test_cursor_movement_spans_fixed_and_stored_rows():
    async with run_pilot() as pilot:
        app = await boot(pilot)
        ptree = app.project_tree

        await new_project(pilot, "only")
        assert highlighted_index(ptree) == 0

        # Up from the first stored project climbs into the fixed block
        await pilot.press("k")
        assert ptree.current_model.uuid == "FixedProject_upcoming"

        await pilot.press("k")
        assert ptree.current_model is TODAY

        # And the top of the pane is the top
        await pilot.press("k")
        assert ptree.current_model is TODAY

        # Down walks back over the project and into the pinned block
        await pilot.press("l", "l")
        assert highlighted_index(ptree) == 0

        await pilot.press("l")
        assert ptree.current_model.uuid == "FixedProject_completed"


async def test_go_to_top_and_bottom_stay_on_stored_projects():
    """`gg` and `G` move between the projects, not the panes' furniture"""

    async with run_pilot() as pilot:
        app = await boot(pilot)
        ptree = app.project_tree

        await new_project(pilot, "one")
        await pilot.press("n")
        await commit_line(pilot, "two")
        await pilot.press("n")
        await commit_line(pilot, "three")

        await pilot.press("g", "g")
        await pilot.pause()
        assert highlighted_index(ptree) == 0

        await pilot.press("G")
        await pilot.pause()
        assert highlighted_index(ptree) == 2


async def test_add_sibling_while_editing_is_refused():
    async with run_pilot() as pilot:
        app = await boot(pilot)
        ptree = app.project_tree

        await pilot.press("j", "n")  # editing now
        ptree.add_sibling()  # refused mid-edit

        await commit_line(pilot, "project")

        assert len(tree_options(ptree)) == 1
        assert highlighted_index(ptree) == 0


async def test_paste_as_sibling():
    async with run_pilot() as pilot:
        app = await boot(pilot)
        ptree = app.project_tree

        await pilot.press("j")
        await pilot.pause()

        set_clipboard(" pasted   project \n")

        # The first paste has nothing to sit beside, so it starts the tree
        await pilot.press("ctrl+v")
        await pilot.pause()

        assert len(tree_options(ptree)) == 1

        # A description is one line, whatever the clipboard was
        assert ptree.current_model.description == "pasted project"

        # And it is a description like any other: `i` opens the edit on the
        # pasted text rather than on the empty string the node was made as
        await pilot.press("i")
        await pilot.pause()
        assert ptree.current.description.value == "pasted project"

        await pilot.press("escape")
        await pilot.pause()
        assert ptree.current_model.description == "pasted project"

        await pilot.press("ctrl+v")
        await pilot.pause()

        assert len(tree_options(ptree)) == 2
        assert highlighted_index(ptree) == 1

        # Nothing on the clipboard is nothing to add
        set_clipboard("   ")
        await pilot.press("ctrl+v")
        await pilot.pause()

        assert len(tree_options(ptree)) == 2


async def test_copy_description():
    async with run_pilot() as pilot:
        app = await boot(pilot)

        await new_project(pilot, "nixos")

        await pilot.press("ctrl+c")
        await pilot.pause()

        assert app.clipboard == "nixos"


async def test_pane_that_fits_has_no_scrollbar(monkeypatch):
    """
    The scrollbar keeps off a projects pane whose rows fit in it

    Completed and Bin are held against the floor by a run of blank lines over
    their rule, and that run is measured off the pane's own height. On the
    first window opened in a process the measurement can be taken before the
    app's stylesheet has been applied, while the pane is still wearing
    OptionList's own padding -- a column either side rather than a line above
    and below -- and so reports two rows of floor it is not going to have.
    The gap that comes out of that is two lines too long, which is exactly
    enough to push the pinned block past the bottom and leave a scrollbar
    standing over a pane that fits.

    The measurement is taken again when the styles land, so a gap worked out
    against the wrong pane does not survive into the drawn one.
    """

    async with run_pilot() as pilot:
        app = await boot(pilot)
        ptree = app.project_tree

        await new_project(pilot, "Work")
        await new_project(pilot, "Home")
        await pilot.pause()

        fitted = ptree._bottom_gap

        # Filled to the floor and no further: the pinned block sits on the
        # last row rather than below it
        assert ptree.virtual_size.height == ptree.scrollable_content_region.height
        assert not ptree.show_vertical_scrollbar

        # The real case gets no resize, but the scrollbar forced up here brings
        # one, which would put the gap right before the styles get the chance
        monkeypatch.setattr(ProjectsTree, "on_resize", lambda self, _: None)

        # The gap a measurement taken against the unstyled pane would leave
        ptree._bottom_gap = fitted + 2
        ptree.refresh_options()
        await pilot.pause()

        assert ptree.show_vertical_scrollbar

        # The word the pane gets that its floor moved
        ptree.notify_style_update()
        await pilot.pause()
        await pilot.pause()

        assert ptree._bottom_gap == fitted
        assert not ptree.show_vertical_scrollbar


async def test_pane_that_overflows_still_scrolls():
    """
    A pane with more rows than it has room for is scrollable, as before

    The gap is what holds the pinned block down while there is floor to spare;
    once the projects have taken all of it there is nothing left to pad with,
    and the block becomes the last thing in a list that scrolls like any
    other.
    """

    async with run_pilot() as pilot:
        app = await boot(pilot)
        ptree = app.project_tree

        for _ in range(ptree.scrollable_content_region.height + 5):
            ptree.add_project()

        ptree.force_refresh()
        await pilot.pause()

        assert ptree._bottom_gap == 0
        assert ptree.virtual_size.height > ptree.scrollable_content_region.height
        assert ptree.show_vertical_scrollbar


async def test_indenting_files_a_project_under_the_row_above():
    """
    I files a project under the row drawn above it, the way it files a task,
    and U takes it back out; the cursor stays on it throughout
    """

    async with run_pilot() as pilot:
        app = await boot(pilot)
        ptree = app.project_tree

        work = await new_project(pilot, "work")
        home = await new_project(pilot, "home")

        # Collapsed: the row has to open again to show where it went
        nested = work.add_project()
        ptree.force_refresh()
        ptree.highlight_id(work.uuid)
        ptree.toggle_expand()
        ptree.highlight_id(home.uuid)
        await pilot.pause()

        await pilot.press("I")
        await pilot.pause()

        assert home.parent_project == work
        assert ptree.current_model == home
        assert len(tree_options(ptree)) == 3
        assert nested.parent_project == work

        await pilot.press("U")
        await pilot.pause()

        assert home.parent_project == work.parent_project
        assert ptree.current_model == home


async def test_indenting_a_project_nowhere_is_turned_away():
    """
    The first project has only the fixed block above it, which holds no
    projects; a top-level project has nothing to come out of; and a fixed
    project can't be moved at all. Each says so and leaves the tree alone.
    """

    async with run_pilot() as pilot:
        app = await boot(pilot)
        ptree = app.project_tree

        first = await new_project(pilot, "first")
        home = first.parent_project

        await pilot.press("I")
        await pilot.pause()
        assert first.parent_project == home
        message = notification_message(app)
        assert message is not None and "No project above" in message

        await pilot.press("U")
        await pilot.pause()
        assert first.parent_project == home
        message = notification_message(app)
        assert message is not None and "not under" in message

        ptree.highlight_id(TODAY.uuid)
        await pilot.pause()

        for key in ("I", "U"):
            await pilot.press(key)
            await pilot.pause()
            assert ptree.current_model is TODAY
            message = notification_message(app)
            assert message is not None and "fixed project" in message

        assert first.parent_project == home


async def test_indenting_a_colored_project_says_it_was_recolored():
    async with run_pilot() as pilot:
        app = await boot(pilot)

        work = await new_project(pilot, "work")
        work.set_color(2)
        home = await new_project(pilot, "home")
        home.set_color(5)

        await pilot.press("I")
        await pilot.pause()

        assert home.color == 2
        message = notification_message(app)
        assert message is not None and "recolored" in message


async def test_a_collapsed_project_stays_collapsed_after_a_relaunch(tmp_path):
    """Expansion is stored with the project, so a relaunch draws the tree as it was left"""

    path = str(tmp_path / "todooit.db")

    async with Todooit(db_path=path).run_test(size=(120, 36)) as pilot:
        app = await boot(pilot)
        ptree = app.project_tree

        outer = await new_project(pilot, "outer")
        inner = outer.add_project()
        inner.description = "inner"
        inner.save()
        ptree.force_refresh()
        ptree.highlight_id(outer.uuid)
        await pilot.pause()

        ptree.toggle_expand()
        await pilot.pause()
        assert inner.uuid not in shown(ptree)

    async with Todooit(db_path=path).run_test(size=(120, 36)) as pilot:
        app = await boot(pilot)
        ptree = app.project_tree

        assert outer.uuid in shown(ptree)
        assert inner.uuid not in shown(ptree)

        ptree.highlight_id(outer.uuid)
        ptree.toggle_expand()
        await pilot.pause()
        assert inner.uuid in shown(ptree)


async def test_always_expand_projects_leaves_the_stored_state_alone():
    async with run_pilot() as pilot:
        app = await boot(pilot)
        ptree = app.project_tree

        outer = await new_project(pilot, "outer")
        inner = outer.add_project()
        inner.description = "inner"
        inner.save()
        outer.set_expanded(False)
        ptree.force_refresh()
        await pilot.pause()
        assert inner.uuid not in shown(ptree)

        app.api.vars.always_expand_projects = True
        ptree.force_refresh()
        await pilot.pause()
        assert inner.uuid in shown(ptree)
        assert not Project.from_id(outer.uuid).expanded

        app.api.vars.always_expand_projects = False
        ptree.force_refresh()
        await pilot.pause()
        assert inner.uuid not in shown(ptree)
