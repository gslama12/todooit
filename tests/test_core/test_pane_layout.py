"""
Pane layout: the finished rows a pane draws, read without booting the app

Guides, the line dropping into a row's family, where families start, banding,
and the headings and context rows of a block.
"""

from datetime import datetime, time, timedelta

from tests.test_core.core_base import *  # noqa
from todooit.api import TODAY, UPCOMING, Project, Todo, TodoGroup, move_todo_to_bin
from todooit.ui.pane_layout import (
    CONTEXT,
    GUIDE_BLANK,
    GUIDE_BRANCH,
    GUIDE_LAST_BRANCH,
    GUIDE_VERTICAL,
    HEADING,
    context_id,
    drawn_children,
    heading_id,
    project_groups,
    todo_rows,
    tree_rows,
)


def everything(_model) -> bool:
    return True


def all_but(*collapsed):
    ids = {model.uuid for model in collapsed}
    return lambda model: model.uuid not in ids


def project_pane(project, expanded=everything, sort_mode=None):
    """The rows a stored project's pane draws"""

    return todo_rows(
        project_groups(project, sort_mode),
        lambda model: drawn_children(model, sort_mode),
        expanded,
    )


def fixed_pane(fixed, expanded=everything):
    return todo_rows(
        fixed.todo_groups, lambda model: drawn_children(model, None), expanded
    )


def name_of(row) -> str:
    """What a row says: a heading its label, any other row its model's description"""

    if not row.uuid:
        return row.label

    kind = Todo if row.uuid.startswith("Todo_") else Project
    return kind.from_id(row.uuid).description


def named(rows):
    return [name_of(row) for row in rows]


def by_name(rows):
    return {name_of(row): row for row in rows}


def today_at(hour: int = 9) -> datetime:
    return datetime.combine(datetime.now().date(), time(hour))


def family(project, *names):
    """A task with steps under it; a name nested in a tuple is a step of the one before"""

    task = project.add_todo()
    task.description = "task"
    task.save()

    made = {"task": task}

    def add(parent, names):
        last = None

        for name in names:
            if isinstance(name, tuple):
                add(last, name)
                continue

            # Each one after the last, as the pane adds them (add_todo files first)
            last = parent.add_todo() if last is None else last.add_sibling()
            last.description = name
            last.save()
            made[name] = last

    add(task, names)
    return made


def test_a_family_is_guided_from_its_root(create_project):
    p = create_project("work")
    family(p, "one", ("deep",), "two")

    rows = by_name(project_pane(p))

    assert rows["task"].is_root and rows["task"].guides == ""
    assert rows["task"].drops

    # Not the last of its family: its line carries on past it
    assert rows["one"].guides == GUIDE_BRANCH
    assert rows["one"].below == GUIDE_VERTICAL
    assert not rows["one"].is_root

    # One level further in, under a row whose line carries on
    assert rows["deep"].guides == GUIDE_VERTICAL + GUIDE_LAST_BRANCH
    assert rows["deep"].below == GUIDE_VERTICAL + GUIDE_BLANK
    assert not rows["deep"].drops

    assert rows["two"].guides == GUIDE_LAST_BRANCH
    assert rows["two"].below == GUIDE_BLANK


def test_a_deep_row_under_a_finished_family_has_a_blank_margin(create_project):
    p = create_project("work")
    family(p, "only", ("deep",))

    rows = by_name(project_pane(p))

    assert rows["deep"].guides == GUIDE_BLANK + GUIDE_LAST_BRANCH


def test_a_collapsed_row_draws_nothing_under_it(create_project):
    p = create_project("work")
    made = family(p, "one", "two")

    rows = project_pane(p, expanded=all_but(made["task"]))

    assert named(rows) == ["task"]
    assert not rows[0].drops


def test_the_last_row_is_the_one_the_sort_draws_last(create_project):
    p = create_project("work")
    made = family(p, "low", "high")

    made["low"].set_priority(3)
    made["low"].save()
    made["high"].set_priority(1)
    made["high"].save()

    rows = project_pane(p, sort_mode="priority")

    assert named(rows) == ["task", "high", "low"]
    assert rows[1].guides == GUIDE_BRANCH
    assert rows[2].guides == GUIDE_LAST_BRANCH


def test_a_step_binned_on_its_own_leaves_its_family(create_project):
    p = create_project("work")
    made = family(p, "kept", "binned")

    move_todo_to_bin(made["binned"])

    rows = project_pane(p)

    assert named(rows) == ["task", "kept"]
    assert rows[1].guides == GUIDE_LAST_BRANCH


def test_sub_projects_are_blocks_under_their_path(create_project):
    p = create_project("work")
    sub = create_project("sub", parent_project=p)
    deeper = create_project("deeper", parent_project=sub)
    create_project("empty", parent_project=p)

    for project, name in ((p, "own"), (sub, "in sub"), (deeper, "in deeper")):
        todo = project.add_todo()
        todo.description = name
        todo.save()

    rows = project_pane(p)
    headings = [row for row in rows if row.kind == HEADING]

    # The empty sub-project has no block, so draws no heading
    assert [row.label for row in headings] == ["sub", "sub/deeper"]
    assert [row.id for row in headings] == [heading_id(1), heading_id(2)]
    assert named(rows) == ["own", "sub", "in sub", "sub/deeper", "in deeper"]


def test_a_block_without_a_label_has_no_heading(create_project):
    p = create_project("work")
    t = p.add_todo()

    rows = todo_rows([TodoGroup(todos=[t])], lambda m: [], everything)

    assert [row.kind for row in rows] == ["model"]


def test_a_context_row_shows_the_work_under_it_even_collapsed(create_project):
    p = create_project("work")
    made = family(p, "planned", "unplanned")

    made["planned"].scheduled = today_at()
    made["planned"].save()

    rows = fixed_pane(TODAY, expanded=all_but(made["task"]))

    # The task is only there to say what the work belongs to
    assert named(rows) == ["work", "task", "planned"]

    context = rows[1]
    assert context.kind == CONTEXT
    assert context.id == context_id(0, made["task"])
    assert context.drops and context.is_root

    assert rows[2].guides == GUIDE_LAST_BRANCH


def test_a_work_row_shows_its_picked_steps_only_while_expanded(create_project):
    p = create_project("work")
    made = family(p, "step")

    for todo in (made["task"], made["step"]):
        todo.scheduled = today_at()
        todo.save()

    assert named(fixed_pane(TODAY)) == ["work", "task", "step"]

    rows = fixed_pane(TODAY, expanded=all_but(made["task"]))
    assert named(rows) == ["work", "task"]
    assert not rows[1].drops


def test_a_task_in_two_blocks_is_laid_out_in_each(create_project):
    """Work today, alone; context tomorrow, over the step planned then"""

    p = create_project("work")
    made = family(p, "later")

    made["task"].scheduled = today_at()
    made["task"].save()
    made["later"].scheduled = today_at() + timedelta(days=1)
    made["later"].save()

    rows = fixed_pane(UPCOMING)
    task = made["task"]

    work = next(row for row in rows if row.id == task.uuid)
    context = next(row for row in rows if row.id == context_id(1, task))

    assert work.block == 0 and not work.drops
    assert context.block == 1 and context.drops


def test_the_projects_tree_guides_sub_projects(create_project):
    top = create_project("top")
    a = create_project("a", parent_project=top)
    create_project("b", parent_project=top)
    create_project("under a", parent_project=a)

    rows = tree_rows([top], lambda project: project.projects, everything)

    assert named(rows) == ["top", "a", "under a", "b"]
    assert [row.guides for row in rows] == [
        "",
        GUIDE_BRANCH,
        GUIDE_VERTICAL + GUIDE_LAST_BRANCH,
        GUIDE_LAST_BRANCH,
    ]
    assert [row.drops for row in rows] == [True, True, False, False]
