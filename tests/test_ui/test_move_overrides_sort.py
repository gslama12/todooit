"""
Moving a row by hand takes the order of the pane over

A pane being read by priority draws its rows wherever the priorities put them,
so K and L had nothing to move: a row shifted one place up in the filing came
straight back down to where the sort wanted it. Moving a row now writes the
order the pane is in into the filing and drops the sort, so the pane looks
exactly as it did and the row goes where it is put — until an order is asked
for again with one of the sort chords.
"""

from todooit.api import Todo
from tests.test_ui.ui_base import (
    commit_line,
    create_and_move_to_todo,
    highlighted_index,
    notification_message,
    run_pilot,
    tree_options,
)
from tests.test_ui.test_sort import seed_unsorted, visible_descriptions


async def move_to_row(pilot, tree, description: str) -> None:
    """Walks the cursor onto the row drawing the named todo, a key at a time"""

    target = visible_descriptions(tree).index(description)

    for _ in range(len(tree_options(tree)) + 1):
        index = highlighted_index(tree)

        if index == target:
            return

        assert index is not None
        await pilot.press("k" if index > target else "l")
        await pilot.pause()

    raise AssertionError(f"never reached {description}")


async def test_shifting_up_drops_the_sort():
    async with run_pilot() as pilot:
        app = pilot.app
        tree = await create_and_move_to_todo(pilot)
        await seed_unsorted(pilot)

        assert visible_descriptions(tree) == ["gamma", "alpha", "beta"]

        await move_to_row(pilot, tree, "alpha")
        await pilot.press("K")
        await pilot.pause()

        assert app.api.vars.todo_sort is None
        assert visible_descriptions(tree) == ["alpha", "gamma", "beta"]


async def test_shifting_down_drops_the_sort():
    async with run_pilot() as pilot:
        app = pilot.app
        tree = await create_and_move_to_todo(pilot)
        await seed_unsorted(pilot)

        await move_to_row(pilot, tree, "gamma")
        await pilot.press("L")
        await pilot.pause()

        assert app.api.vars.todo_sort is None
        assert visible_descriptions(tree) == ["alpha", "gamma", "beta"]


async def test_the_pane_is_left_exactly_as_it_was_drawn():
    """Dropping the sort moves nothing by itself: only the shift does"""

    async with run_pilot() as pilot:
        tree = await create_and_move_to_todo(pilot)
        await seed_unsorted(pilot)

        # The last row, which has nowhere further down to go: the shift is
        # turned down and the order on screen is the sorted one, now filed
        await move_to_row(pilot, tree, "beta")
        await pilot.press("L")
        await pilot.pause()

        assert visible_descriptions(tree) == ["gamma", "alpha", "beta"]
        assert [t.order_index for t in Todo.all()] == [2, 1, 0]


async def test_the_bar_says_the_order_changed_hands():
    async with run_pilot() as pilot:
        app = pilot.app
        tree = await create_and_move_to_todo(pilot)
        await seed_unsorted(pilot)

        await move_to_row(pilot, tree, "alpha")
        await pilot.press("K")
        await pilot.pause()

        message = notification_message(app)
        assert message is not None and "Order is yours now" in message


async def test_a_second_shift_says_nothing_more():
    """The bar speaks on the handover, not on every move afterwards"""

    async with run_pilot() as pilot:
        app = pilot.app
        tree = await create_and_move_to_todo(pilot)
        await seed_unsorted(pilot)

        await move_to_row(pilot, tree, "beta")
        await pilot.press("K")
        await pilot.pause()

        app.bar_switcher.current = "status_bar"
        await pilot.pause()

        await pilot.press("K")
        await pilot.pause()

        assert notification_message(app) is None


async def test_sorting_again_rearranges_the_rows():
    async with run_pilot() as pilot:
        app = pilot.app
        tree = await create_and_move_to_todo(pilot)
        await seed_unsorted(pilot)

        await move_to_row(pilot, tree, "alpha")
        await pilot.press("K")
        await pilot.pause()

        assert visible_descriptions(tree) == ["alpha", "gamma", "beta"]

        await pilot.press("S", "P")
        await pilot.pause()

        assert app.api.vars.todo_sort == "priority"
        assert visible_descriptions(tree) == ["gamma", "alpha", "beta"]


async def seed_steps(pilot, tree):
    """A task with three steps whose priorities disagree with their filing"""

    await pilot.press("n")
    await commit_line(pilot, "task")

    # Only the first one is filed under the task: the ones after it are made
    # beside it, which puts them under the task too. Indenting every one of
    # them would build a chain of steps each inside the last
    await pilot.press("n")
    await commit_line(pilot, "first")
    await pilot.press("I")
    await pilot.pause()

    for name in ("second", "third"):
        await pilot.press("n")
        await commit_line(pilot, name)

    first, second, third = (t for t in Todo.all() if t.description != "task")
    assert [t.parent_todo and t.parent_todo.description for t in (first, second, third)] == ["task"] * 3

    second.priority = 1
    second.save()
    third.priority = 2
    third.save()

    await pilot.pause()
    tree.force_refresh()
    await pilot.pause()

    return first, second, third


async def test_shifting_a_step_drops_the_sort():
    """The steps of a task are read by the same order, and moved the same way"""

    async with run_pilot() as pilot:
        app = pilot.app
        tree = await create_and_move_to_todo(pilot)
        await seed_steps(pilot, tree)

        assert visible_descriptions(tree) == [
            "task",
            "second",
            "third",
            "first",
        ]

        await move_to_row(pilot, tree, "third")
        await pilot.press("K")
        await pilot.pause()

        assert app.api.vars.todo_sort is None
        assert visible_descriptions(tree) == [
            "task",
            "third",
            "second",
            "first",
        ]


async def test_sorting_again_rearranges_the_steps():
    async with run_pilot() as pilot:
        app = pilot.app
        tree = await create_and_move_to_todo(pilot)
        await seed_steps(pilot, tree)

        await move_to_row(pilot, tree, "third")
        await pilot.press("K")
        await pilot.pause()

        await pilot.press("S", "P")
        await pilot.pause()

        assert app.api.vars.todo_sort == "priority"
        assert visible_descriptions(tree) == [
            "task",
            "second",
            "third",
            "first",
        ]
