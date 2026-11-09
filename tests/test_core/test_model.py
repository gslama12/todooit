from tests.test_core.core_base import *  # noqa
from todooit.api import Project, Todo, manager


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


# ------------------- Expansion state --------------------


def test_new_rows_start_expanded(create_project, create_todo):
    assert create_project().expanded
    assert create_todo().expanded


def test_set_expanded_saves_only_a_change(create_project):
    project = create_project()
    revision = manager.revision

    project.set_expanded(True)
    assert manager.revision == revision

    project.set_expanded(False)
    assert manager.revision == revision + 1
    assert not project.expanded


def test_expansion_survives_a_reconnect(tmp_path):
    path = str(tmp_path / "todooit.db")
    manager.connect(path)

    project = Project(description="folded")
    project.save()
    todo = project.add_todo()
    todo.description = "folded task"
    todo.save()

    project.set_expanded(False)
    todo.set_expanded(False)
    project_id, todo_id = project.uuid, todo.uuid
    manager.session.close()

    manager.connect(path)

    assert not Project.from_id(project_id).expanded
    assert not Todo.from_id(todo_id).expanded
    manager.session.close()


def test_a_database_from_before_expansion_gets_the_column(tmp_path):
    path = str(tmp_path / "todooit.db")
    manager.connect(path)

    project = Project(description="old")
    project.save()
    todo = project.add_todo()
    todo.save()
    project_id, todo_id = project.uuid, todo.uuid
    manager.session.close()

    # What a database written before the column existed looks like
    with manager.engine.begin() as connection:
        connection.exec_driver_sql("ALTER TABLE todo DROP COLUMN expanded")
        connection.exec_driver_sql("ALTER TABLE project DROP COLUMN expanded")

    manager.connect(path)

    assert Project.from_id(project_id).expanded
    assert Todo.from_id(todo_id).expanded

    # And it can be written
    Project.from_id(project_id).set_expanded(False)
    assert not Project.from_id(project_id).expanded
    manager.session.close()
