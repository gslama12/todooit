from tests.test_core.core_base import *  # noqa
from todooit.api.project import Project


def test_creation_and_deletion(create_project):
    p = create_project()
    assert len(Project.all()) == 1

    p.drop()
    assert len(Project.all()) == 0


def test_shifts_normal(create_project):
    project = [create_project() for _ in range(5)][0]
    assert project is not None

    siblings = project.siblings
    assert project.is_first_sibling()

    project.shift_down()
    siblings = project.siblings
    assert siblings[1].id == project.id

    project.shift_up()
    siblings = project.siblings
    assert siblings[0].id == project.id
    assert project.is_first_sibling()


def test_shifts_edge(create_project):
    projects = [create_project() for _ in range(5)]

    assert not projects[0].shift_up()
    assert not projects[-1].shift_down()


def test_swap_with_exchanges_places(create_project):
    projects = [create_project() for _ in range(5)]
    first, last = projects[0], projects[-1]

    assert first.swap_with(last)
    assert [p.id for p in first.siblings] == [
        last.id,
        *[p.id for p in projects[1:-1]],
        first.id,
    ]


def test_swap_with_refuses_anything_not_beside_it(create_project):
    """Only a sibling is a place to swap into — itself included, which is none"""

    parent = create_project()
    child = create_project(parent_project=parent)
    stranger = create_project()

    assert not child.swap_with(child)
    assert not child.swap_with(stranger)


def test_shifts_across_a_run_filed_with_holes(create_project):
    """
    One press, one place, whatever the run is numbered

    A run built up by hand can have holes in it. Nudging the two indexes past
    each other by one used to leave the pair still in the order they were in,
    so the key had to be pressed as many times as the gap was wide before
    anything moved.
    """

    projects = [create_project() for _ in range(3)]

    for project, order in zip(projects, (0, 6, 9)):
        project.order_index = order
        project.save()

    first = projects[0]
    assert first.shift_down()
    assert [p.id for p in first.siblings] == [
        projects[1].id,
        first.id,
        projects[2].id,
    ]


def test_shifts_across_a_run_filed_at_one_index(create_project):
    """Two items filed at the same index still swap rather than stick"""

    projects = [create_project() for _ in range(3)]

    for project in projects:
        project.order_index = 0
        project.save()

    first, second = projects[0].siblings[:2]
    assert first.shift_down()
    assert [p.id for p in first.siblings][:2] == [second.id, first.id]
