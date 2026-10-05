"""
The guides drawn in front of a nested row: where the elbow lands, and how far
down the row it carries

Two things the guides have to follow rather than guess at: the order the pane
reads its rows in, which is not the order they are filed in, and the height of
the rows themselves, which a description long enough to wrap makes more than
one line of.
"""

import re
from typing import List

from rich.console import Console

from todooit.api import Todo, move_todo_to_bin
from todooit.ui.pane_layout import (
    GUIDE_BLANK,
    GUIDE_BRANCH,
    GUIDE_DROP,
    GUIDE_LAST_BRANCH,
    GUIDE_VERTICAL,
    context_id,
)
from todooit.ui.widgets.trees.model_tree import ModelTree
from tests.test_ui.ui_base import (
    boot,
    commit_line,
    create_and_move_to_todo,
    run_pilot,
    visible_todos,
)

# Narrow enough that a sentence of a description has to wrap, wide enough that
# it still wraps a word at a time rather than a letter at a time
PANE_WIDTH = 80

# The gap the pane keeps in front of its first column, which the guides of a
# nested row are drawn in rather than in front of
INSET = "  "


def drop_column(depth: int) -> int:
    """
    Where the line into the family of a row at `depth` is drawn

    Out of the row's own first column, which is where the elbows of whatever
    hangs off it turn: one guide further along for every level it is in.
    """

    return len(INSET) + depth * len(GUIDE_BRANCH)


LONG = "a step whose description runs on well past the end of the pane it is drawn in"

# What is drawn is counted in columns, and the styling a row comes with is not
# any of them: rich still writes bold and dim out even with the colors off
ANSI = re.compile(r"\x1b\[[0-9;]*m")


def row_lines(tree: ModelTree, model, width: int = PANE_WIDTH) -> List[str]:
    """Every line a row is drawn as, in a pane of the given width"""

    console = Console(width=width, no_color=True, legacy_windows=False)

    with console.capture() as capture:
        console.print(tree.prompt_for(model.uuid), end="")

    return ANSI.sub("", capture.get()).rstrip("\n").split("\n")


def guides_of(tree: ModelTree, model) -> str:
    return tree._rows[model.uuid].guides


async def seed_steps(pilot) -> Todo:
    """A task with three steps under it, filed low / high / mid by priority"""

    await pilot.press("n")
    await commit_line(pilot, "task")

    await pilot.press("N")
    await commit_line(pilot, "step low")
    await pilot.press("n")
    await commit_line(pilot, "step high")
    await pilot.press("n")
    await commit_line(pilot, "step mid")
    await pilot.pause()

    task = next(todo for todo in Todo.all() if todo.description == "task")

    for step, priority in zip(task.todos, (3, 1, 2)):
        step.set_priority(priority)
        step.save()

    return task


async def test_the_elbow_lands_on_the_row_the_pane_draws_last():
    """
    A sorted family ends on the row the sort put at the bottom of it

    The steps are filed low / high / mid and read high / mid / low: the elbow
    belongs to the one the pane draws last, not to the one the database does.
    """

    async with run_pilot() as pilot:
        tree = await create_and_move_to_todo(pilot)
        task = await seed_steps(pilot)

        tree.sort_by("priority")
        await pilot.pause()

        high, mid, low = tree.visible_children(task)
        assert [step.description for step in (high, mid, low)] == [
            "step high",
            "step mid",
            "step low",
        ]

        # Filed last, drawn in the middle: nothing about the filing shows
        assert mid.is_last_sibling()

        assert guides_of(tree, high) == GUIDE_BRANCH
        assert guides_of(tree, mid) == GUIDE_BRANCH
        assert guides_of(tree, low) == GUIDE_LAST_BRANCH


async def test_a_step_the_pane_leaves_out_does_not_end_the_family():
    """
    A binned step is gone from the pane, and the elbow moves up to what is left

    The row it was drawn beside is now the last one there, however the step it
    outlived is still filed after it.
    """

    async with run_pilot() as pilot:
        tree = await create_and_move_to_todo(pilot)
        task = await seed_steps(pilot)

        tree.sort_by("priority")
        await pilot.pause()

        high, mid, low = tree.visible_children(task)

        # The last row drawn, thrown away: the elbow has to fall back to `mid`
        move_todo_to_bin(low)
        tree._refresh_and_restore_highlight()
        await pilot.pause()

        assert tree.visible_children(task) == [high, mid]
        assert guides_of(tree, high) == GUIDE_BRANCH
        assert guides_of(tree, mid) == GUIDE_LAST_BRANCH


async def test_a_wrapped_step_keeps_the_guides_under_it():
    """
    A row tall enough to wrap is guided on every line, not only on its first

    The elbow is spent on the first line; below it the row still has to stand
    in the margin its family is drawn in, with the line of whatever carries on
    past it drawn down the side.
    """

    async with run_pilot() as pilot:
        tree = await create_and_move_to_todo(pilot)

        await pilot.press("n")
        await commit_line(pilot, "task")

        await pilot.press("N")
        await commit_line(pilot, LONG)
        await pilot.press("n")
        await commit_line(pilot, "last " + LONG)
        await pilot.pause()

        task = next(todo for todo in Todo.all() if todo.description == "task")
        first, last = tree.visible_children(task)

        wrapped = row_lines(tree, first)
        assert len(wrapped) > 1
        assert wrapped[0].startswith(INSET + GUIDE_BRANCH)

        # Another row is drawn below it, so its line carries on down the side
        for line in wrapped[1:]:
            assert line.startswith(INSET + GUIDE_VERTICAL)

        ended = row_lines(tree, last)
        assert len(ended) > 1
        assert ended[0].startswith(INSET + GUIDE_LAST_BRANCH)

        # Nothing left beside it: the margin stays, the line in it does not
        for line in ended[1:]:
            assert line.startswith(INSET + GUIDE_BLANK)

        # Neither of them has anything of its own under it, so neither has a
        # line dropping out of its first column into a family that isn't there
        for line in wrapped[1:] + ended[1:]:
            assert line[drop_column(1)] == " "


async def test_a_wrapped_row_carries_the_drop_into_its_own_family():
    """
    A row that wraps keeps the line into what hangs off it running through it

    What hangs off a row turns out of the row's own first column, and starts
    on the line after the last of the row's own. Between the two the line has
    to be drawn through the row rather than around it, or the family it opens
    hangs off nothing.
    """

    async with run_pilot() as pilot:
        tree = await create_and_move_to_todo(pilot)

        await pilot.press("n")
        await commit_line(pilot, "task")
        await pilot.press("N")
        await commit_line(pilot, LONG)
        await pilot.press("N")
        await commit_line(pilot, "a step of the step")
        await pilot.pause()

        task = next(todo for todo in Todo.all() if todo.description == "task")
        (parent,) = tree.visible_children(task)
        (child,) = tree.visible_children(parent)

        lines = row_lines(tree, parent)
        assert len(lines) > 1

        # The row is the only one of its family, so its own level has run out
        # while the level below it is only just opening
        for line in lines[1:]:
            assert line.startswith(INSET + GUIDE_BLANK)
            assert line[drop_column(1)] == GUIDE_DROP

        # And the line it was drawn down to is the elbow of the row below
        assert row_lines(tree, child)[0][drop_column(1)] == GUIDE_LAST_BRANCH[0]


async def test_a_wrapped_row_at_the_top_of_the_tree_carries_the_drop_too():
    """
    Nothing in front of a top level row, and still a line out of it

    Its family hangs off it the same way a nested one does; what it has none
    of is guides of its own, which is not the same as having nothing under it.
    """

    async with run_pilot() as pilot:
        tree = await create_and_move_to_todo(pilot)

        await pilot.press("n")
        await commit_line(pilot, "a task " + LONG)
        await pilot.press("N")
        await commit_line(pilot, "a step of it")
        await pilot.pause()

        (task,) = tree.visible_children(tree.model)
        (step,) = tree.visible_children(task)

        lines = row_lines(tree, task)
        assert len(lines) > 1
        assert guides_of(tree, task) == ""

        for line in lines[1:]:
            assert len(line) == PANE_WIDTH
            assert line[drop_column(0)] == GUIDE_DROP

        assert row_lines(tree, step)[0][drop_column(0)] == GUIDE_LAST_BRANCH[0]


async def test_a_wrapped_row_stays_in_its_own_columns():
    """
    Every line of a row is as wide as the pane and starts where the row does

    What the guides push to the right is the whole row: a second line that
    came back to the left edge would run under the family it hangs off.
    """

    async with run_pilot() as pilot:
        tree = await create_and_move_to_todo(pilot)

        await pilot.press("n")
        await commit_line(pilot, "task")
        await pilot.press("N")
        await commit_line(pilot, LONG)
        await pilot.pause()

        task = next(todo for todo in Todo.all() if todo.description == "task")
        (step,) = tree.visible_children(task)

        margin = len(INSET + GUIDE_BRANCH)
        lines = row_lines(tree, step)
        assert len(lines) > 1

        for line in lines:
            assert len(line) == PANE_WIDTH
            assert line[margin:].lstrip() != ""


async def test_a_nested_row_lines_up_with_the_one_it_hangs_off():
    """
    The guides shift a row by their own width and by nothing else

    A row drawn one level in keeps the pane's columns: its description starts
    one guide further along than its parent's, and the columns after it end
    where every other row's do, since the pane is one set of columns however
    deep it is read.
    """

    async with run_pilot() as pilot:
        tree = await create_and_move_to_todo(pilot)

        await pilot.press("n")
        await commit_line(pilot, "task")
        await pilot.press("N")
        await commit_line(pilot, "step")
        await pilot.pause()

        task = next(todo for todo in Todo.all() if todo.description == "task")
        (step,) = tree.visible_children(task)

        (parent_line,) = row_lines(tree, task)
        (step_line,) = row_lines(tree, step)

        assert len(parent_line) == len(step_line) == PANE_WIDTH

        # Pushed right by the guides in front of it, and by nothing else
        shift = step_line.index("step") - parent_line.index("task")
        assert shift == len(GUIDE_LAST_BRANCH)

        # The columns past the description belong to the pane, not to the row:
        # the dashes standing in for the empty ones fall in the same places
        def dashes(line: str) -> List[int]:
            return [index for index, char in enumerate(line) if char == "-"]

        assert dashes(step_line) == dashes(parent_line)


async def test_a_wrapped_project_keeps_the_guides_under_it():
    """
    The projects pane guides a wrapped row the same way the tasks pane does

    Its description is the first column rather than the second, which is where
    a guide glued to the front of the text used to vanish from: the text came
    back to the left edge on its second line and ran straight through them.
    """

    async with run_pilot() as pilot:
        app = await boot(pilot)
        tree = app.project_tree

        parent = tree.model.add_project()
        parent.description = "a parent project"
        parent.save()

        child = parent.add_project()
        child.description = (
            "a sub project whose name runs on well past the end of the pane"
        )
        child.save()

        tree._refresh_and_restore_highlight()
        await pilot.pause()

        lines = row_lines(tree, child, width=40)
        assert len(lines) > 1
        assert lines[0].startswith(INSET + GUIDE_LAST_BRANCH)

        margin = len(INSET + GUIDE_BLANK)

        for line in lines[1:]:
            assert line.startswith(INSET + GUIDE_BLANK)
            assert line[margin:].lstrip() != ""

        # Nothing is drawn under it, so nothing wants the column its name
        # wraps into: the name carries straight on under where it started
        assert lines[1].index("name") == margin


async def test_a_project_with_children_carries_the_drop_through_its_name():
    """
    The projects pane grows the branch through a wrapped name, as the tasks do

    Its description is the pane's first column, which is the column the rows
    under it turn out of. The name hangs in from its second line to leave that
    column free: a pane cannot draw the line and the name in the same place.
    """

    async with run_pilot() as pilot:
        app = await boot(pilot)
        tree = app.project_tree

        parent = tree.model.add_project()
        parent.description = "a parent project whose name runs past the end of the pane"
        parent.save()

        child = parent.add_project()
        child.description = "a sub project"
        child.save()

        tree._refresh_and_restore_highlight()
        await pilot.pause()

        lines = row_lines(tree, parent, width=40)
        assert len(lines) > 1

        drop = drop_column(0)

        for line in lines[1:]:
            assert line[drop] == GUIDE_DROP

            # The name stepped aside for it rather than being drawn over
            assert line[drop + 1 : drop + len(GUIDE_VERTICAL)].strip() == ""
            assert line[drop + len(GUIDE_VERTICAL) :].lstrip() != ""

        # The line it was drawn down to is the elbow of the row below it
        assert row_lines(tree, child, width=40)[0][drop] == GUIDE_LAST_BRANCH[0]


async def test_a_description_too_long_for_its_column_is_folded_not_cut():
    """
    A description wider than the column it is drawn in wraps, and is never cut

    Everything a row says is worth reading, and the word a narrow pane runs
    out of room for is not the one worth losing: it is carried onto the next
    line rather than quietly swapped for an ellipsis.
    """

    words = "alpha bravo charlie delta echo foxtrot golf hotel india juliet"
    long_word = "supercalifragilisticexpialidocious"

    async with run_pilot() as pilot:
        tree = await create_and_move_to_todo(pilot)

        await pilot.press("n")
        await commit_line(pilot, words)
        await pilot.press("n")
        await commit_line(pilot, long_word)
        await pilot.pause()

        wrapped, folded = tree.visible_children(tree.model)

        # Every other column of these rows is empty, so the letters drawn
        # anywhere on them are the description and nothing else
        def letters(lines: List[str]) -> str:
            return "".join(re.findall(r"[a-z]+", " ".join(lines)))

        # Nowhere near wide enough to hold the description on one line
        lines = row_lines(tree, wrapped, width=60)
        assert len(lines) > 1
        assert "…" not in " ".join(lines)
        assert letters(lines) == words.replace(" ", "")

        # A single word longer than the column has nowhere to wrap: it is
        # folded across lines rather than having its tail taken off
        lines = row_lines(tree, folded, width=60)
        assert len(lines) > 1
        assert "…" not in " ".join(lines)
        assert letters(lines) == long_word


async def test_a_task_in_two_day_blocks_takes_its_guides_from_each():
    """
    Upcoming draws a task planned for today as work there, alone, and as
    context tomorrow over the step planned then: the line down into a family
    runs out of the context row only, since only there is anything under it
    """

    async with run_pilot() as pilot:
        app = await boot(pilot)
        await create_and_move_to_todo(pilot)

        await pilot.press("n")
        await commit_line(pilot, LONG)
        await pilot.press("s")
        await commit_line(pilot, "today")

        await pilot.press("N")
        await commit_line(pilot, "later")
        await pilot.press("s")
        await commit_line(pilot, "tomorrow")

        await pilot.press("g", "u")
        await pilot.pause()

        upcoming = visible_todos(app)
        task = next(todo for todo in Todo.all() if todo.description == LONG)

        def lines(_id: str) -> List[str]:
            console = Console(width=PANE_WIDTH, no_color=True, legacy_windows=False)

            with console.capture() as capture:
                console.print(upcoming.prompt_for(_id), end="")

            return ANSI.sub("", capture.get()).rstrip("\n").split("\n")

        work = lines(task.uuid)
        context = lines(context_id(1, task))
        assert len(work) > 1 and len(context) > 1

        assert all(line[drop_column(0)] == " " for line in work[1:])
        assert all(line[drop_column(0)] == GUIDE_DROP for line in context[1:])
