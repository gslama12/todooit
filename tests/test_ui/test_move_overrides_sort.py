"""
Moving a row by hand takes the order of the pane over

A pane being read by priority draws its rows wherever the priorities put them,
so K and L had nothing to move: a row shifted one place up in the filing came
straight back down to where the sort wanted it. Moving a row now writes the
order the pane is in into the filing and drops the sort, so the pane looks
exactly as it did and the row goes where it is put — until an order is asked
for again with one of the sort chords.

The other half of the same idea is at the bottom of this file: a move goes by
the row drawn beside the cursor, not by the row filed beside it. The pane
leaves part of the run out — a task ticked off is drawn in Completed and one
thrown away in the Bin, and both are still filed here — and a move that
stepped through the filing spent a press on each of those without anything on
screen moving.
"""

from datetime import datetime

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


# ------------------------------------------------------------------
# Moving by the row on screen, not by the row in the filing
# ------------------------------------------------------------------


async def seed_with_a_hidden_row(pilot, tree, hide: str):
    """
    Four tasks filed a-b-c-d with "b" drawn somewhere else entirely

    `hide` says how it leaves: ticked off, so it is drawn in Completed, or
    thrown away, so it is drawn in the Bin. Either way it keeps its place in
    the filing, sitting between the rows this pane does draw.
    """

    for name in ("a", "b", "c", "d"):
        await pilot.press("n")
        await commit_line(pilot, name)

    a, b, c, d = Todo.all()

    if hide == "completed":
        b.toggle_complete()
    else:
        b.binned_at = datetime.now()

    b.save()

    await pilot.pause()
    tree.force_refresh()
    await pilot.pause()

    assert visible_descriptions(tree) == ["a", "c", "d"]

    return a, b, c, d


async def test_moving_down_over_a_completed_row_takes_one_press():
    """
    The row below "a" on screen is "c", so one L is what it takes to pass it

    Stepping through the filing put "a" past the completed "b" instead, which
    moved nothing on screen and made the key look like it had missed.
    """

    async with run_pilot() as pilot:
        tree = await create_and_move_to_todo(pilot)
        await seed_with_a_hidden_row(pilot, tree, "completed")

        await move_to_row(pilot, tree, "a")
        await pilot.press("L")
        await pilot.pause()

        assert visible_descriptions(tree) == ["c", "a", "d"]


async def test_moving_up_over_a_completed_row_takes_one_press():
    async with run_pilot() as pilot:
        tree = await create_and_move_to_todo(pilot)
        await seed_with_a_hidden_row(pilot, tree, "completed")

        await move_to_row(pilot, tree, "c")
        await pilot.press("K")
        await pilot.pause()

        assert visible_descriptions(tree) == ["c", "a", "d"]


async def test_moving_over_a_binned_row_takes_one_press():
    """A row in the Bin is out of the pane the same way a completed one is"""

    async with run_pilot() as pilot:
        tree = await create_and_move_to_todo(pilot)
        await seed_with_a_hidden_row(pilot, tree, "binned")

        await move_to_row(pilot, tree, "a")
        await pilot.press("L")
        await pilot.pause()

        assert visible_descriptions(tree) == ["c", "a", "d"]


async def test_the_hidden_row_is_left_where_it_was_filed():
    """Passing a row the pane never drew does not drag it along"""

    async with run_pilot() as pilot:
        tree = await create_and_move_to_todo(pilot)
        _, b, _, _ = await seed_with_a_hidden_row(pilot, tree, "completed")

        await move_to_row(pilot, tree, "a")
        await pilot.press("L")
        await pilot.pause()

        filed = sorted(Todo.all(), key=lambda todo: todo.order_index)
        assert [todo.description for todo in filed] == ["c", "b", "a", "d"]


async def test_a_row_walks_the_whole_pane_a_press_at_a_time():
    """
    Every press moves it one row, and the last one is turned down

    The end of the run is the end of what the pane draws, so the walk is three
    presses long and the fourth has nowhere to go — rather than the row
    burying itself among the ones that are filed here but drawn elsewhere.
    """

    async with run_pilot() as pilot:
        tree = await create_and_move_to_todo(pilot)
        await seed_with_a_hidden_row(pilot, tree, "completed")

        await move_to_row(pilot, tree, "a")

        for expected in (["c", "a", "d"], ["c", "d", "a"], ["c", "d", "a"]):
            await pilot.press("L")
            await pilot.pause()
            assert visible_descriptions(tree) == expected


async def test_a_step_moves_past_a_completed_step_in_one_press():
    """The steps of a task hide the same rows, and are moved the same way"""

    async with run_pilot() as pilot:
        tree = await create_and_move_to_todo(pilot)

        await pilot.press("n")
        await commit_line(pilot, "task")

        await pilot.press("n")
        await commit_line(pilot, "one")
        await pilot.press("I")
        await pilot.pause()

        for name in ("two", "three"):
            await pilot.press("n")
            await commit_line(pilot, name)

        one, two, three = (t for t in Todo.all() if t.description != "task")

        # A step ticked off stays under its task, so it has to be the Bin that
        # takes it out of the run rather than completion
        two.binned_at = datetime.now()
        two.save()

        await pilot.pause()
        tree.force_refresh()
        await pilot.pause()

        assert visible_descriptions(tree) == ["task", "one", "three"]

        await move_to_row(pilot, tree, "one")
        await pilot.press("L")
        await pilot.pause()

        assert visible_descriptions(tree) == ["task", "three", "one"]
