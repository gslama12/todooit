"""
Placement: where a todo lives (its home), its root, its bin row and its project

Rules R1-R4 of the placement glossary, the rule that an orphan is always
binned, and the tripwire that keeps the Bin's own gathering in step with
placement.
"""

from tests.test_core.core_base import *  # noqa
from todooit.api import (
    BIN,
    Todo,
    move_project_to_bin,
    move_todo_to_bin,
    restore_todo,
)
from todooit.ui.pane_layout import drawn_children
from todooit.api.placement import (
    bin_row_of,
    home_of,
    project_of,
    root_of,
)


def test_a_binned_todo_lives_in_the_bin(create_project):
    """R1"""

    p = create_project("work")
    root = p.add_todo()

    move_todo_to_bin(root)

    assert home_of(root) is BIN


def test_a_step_binned_on_its_own_lives_in_the_bin_as_its_own_bin_row(
    create_project,
):
    """R1: even though its parent is not binned"""

    p = create_project("work")
    root = p.add_todo()
    step = root.add_todo()

    move_todo_to_bin(step)

    assert home_of(step) is BIN
    assert bin_row_of(step) is step
    assert home_of(root) is p


def test_a_completed_root_stays_in_its_project_with_its_steps(create_project):
    """R2"""

    p = create_project("work")
    root = p.add_todo()
    step = root.add_todo()
    sub_step = step.add_todo()

    root.toggle_complete()

    assert home_of(root) is p
    assert home_of(step) is p
    assert home_of(sub_step) is p


def test_a_completed_step_under_an_open_root_stays_under_it(create_project):
    """R3: a step finished on its own stays where it is, drawn only when shown"""

    p = create_project("work")
    root = p.add_todo()
    done = root.add_todo()
    root.add_todo()

    done.toggle_complete()

    assert root.is_pending
    assert home_of(root) is p
    assert home_of(done) is p
    assert done in drawn_children(root, None, show_completed=True)
    assert done not in drawn_children(root, None, show_completed=False)


def test_an_open_todo_in_a_nested_project_lives_in_that_project(create_project):
    """R3: its project is the one it is filed under, however deep"""

    work = create_project("work")
    api = create_project("api", parent_project=work)
    root = api.add_todo()
    step = root.add_todo()
    sub_step = step.add_todo()

    assert project_of(sub_step) is api
    assert home_of(sub_step) is api
    assert root_of(sub_step) is root


def test_a_step_binned_with_its_root_is_drawn_in_its_root_s_bin_row(create_project):
    """R1: the bin row is the highest binned todo in the line"""

    p = create_project("work")
    root = p.add_todo()
    step = root.add_todo()
    sub_step = step.add_todo()

    move_todo_to_bin(root)

    assert home_of(sub_step) is BIN
    assert bin_row_of(sub_step) is root


def test_an_open_orphan_restored_gets_its_project_back(create_project):
    """R4"""

    work = create_project("work")
    root = work.add_todo()

    move_project_to_bin(work)
    assert project_of(root) is None
    assert home_of(root) is BIN

    restore_todo(root)

    home = home_of(root)
    assert home is project_of(root)
    assert home is not None and home.description.endswith("work")


def test_a_restored_completed_orphan_gets_its_project_back_still_completed(
    create_project,
):
    """R4: open or completed, a restored task goes home"""

    work = create_project("work")
    root = work.add_todo()
    step = root.add_todo()
    root.toggle_complete()

    move_project_to_bin(work)
    restore_todo(step)

    home = project_of(root)
    assert home is not None and home.description == "revived - work"
    assert home_of(root) is home
    assert home_of(step) is home
    assert root.is_completed and step.is_completed
    assert root.origin_path == ""


def assert_orphans_are_binned() -> None:
    for todo in Todo.all():
        if todo.is_orphan:
            assert todo.is_binned, todo.description


def test_an_orphan_is_always_binned(create_project):
    """The rule: every todo outside the Bin has a project, after every move"""

    work = create_project("work")
    done = work.add_todo()
    done.description = "done"
    done.add_todo()
    open_one = work.add_todo()
    open_one.description = "open"
    open_one.add_todo()

    done.toggle_complete()
    assert_orphans_are_binned()

    move_project_to_bin(work)
    assert_orphans_are_binned()

    restore_todo(done)
    assert_orphans_are_binned()

    done.toggle_complete()
    assert_orphans_are_binned()

    done.toggle_complete()
    restore_todo(open_one)
    assert_orphans_are_binned()

    assert all(t.is_binned or project_of(t) is not None for t in Todo.all())


def test_the_bin_gathers_exactly_what_lives_there(create_project):
    """
    The tripwire: the Bin keeps its own fast gathering, and it must agree with
    placement over a tree of every kind of todo
    """
    work = create_project("work")
    api = create_project("api", parent_project=work)
    house = create_project("my house")
    garden = create_project("garden", parent_project=house)

    # open, with a completed step and a step binned on its own
    open_root = api.add_todo()
    open_done = open_root.add_todo()
    open_done.toggle_complete()
    move_todo_to_bin(open_root.add_todo().add_todo())
    open_root.add_todo()

    # completed, with a step binned on its own after the fact
    done_root = work.add_todo()
    done_root.add_todo()
    done_root.toggle_complete()
    move_todo_to_bin(done_root.add_todo())

    # binned whole, binned after completing, and binned then restored
    move_todo_to_bin(house.add_todo())
    finished = house.add_todo()
    finished.add_todo()
    finished.toggle_complete()
    move_todo_to_bin(finished)
    back = house.add_todo()
    back.add_todo()
    move_todo_to_bin(back)
    restore_todo(back)

    # orphans: a binned project's open and completed todos, one of each restored
    garden.add_todo().add_todo()
    garden.add_todo().toggle_complete()
    open_orphan = garden.add_todo()
    done_orphan = garden.add_todo()
    done_orphan.add_todo()
    done_orphan.toggle_complete()
    move_project_to_bin(garden)
    restore_todo(open_orphan)
    restore_todo(done_orphan)

    everything = Todo.all()

    # No todo is left without a home: an orphan is always binned
    assert all(home_of(t) is not None for t in everything)

    bin_rows = {t.id for t in everything if home_of(t) is BIN and bin_row_of(t) is t}

    assert {t.id for t in BIN.todos} == bin_rows

    # Every kind made it in, so the agreement above means something
    assert len(bin_rows) == 6
