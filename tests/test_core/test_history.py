"""
The undo history: what a change is worth keeping, and what putting one back does
"""

from datetime import datetime

from tests.test_core.core_base import *  # noqa
from todooit.api import History, Project, Todo, manager, move_project_to_bin
from todooit.api.history import MAX_DEPTH


def started_history() -> History:
    history = History()
    history.start()
    return history


def descriptions(model) -> list:
    return sorted(row.description for row in model.all())


def test_nothing_recorded_without_a_write():
    history = started_history()

    assert not history.record()
    assert not history._undo


def test_a_write_that_changed_nothing_is_not_a_change(create_project):
    project = create_project("unchanged")
    history = started_history()

    # A save that writes the field back the way it found it still commits
    project.description = "unchanged"
    project.save()

    assert not history.record()
    assert not history._undo


def test_adding_is_taken_back(create_project):
    history = started_history()
    create_project("new")

    assert history.record()
    assert history._undo

    restored = history.undo()

    assert restored is not None
    assert Project.all() == []
    assert restored.gone == ["Project_2"]
    assert restored.summary() == "1 row dropped"


def test_what_was_taken_back_can_be_put_back(create_project):
    history = started_history()
    project = create_project("new")
    todo = project.add_todo()
    todo.description = "work"
    todo.save()

    history.record()
    history.undo()

    assert Project.all() == []
    assert Todo.all() == []

    restored = history.redo()

    assert restored is not None
    assert descriptions(Project) == ["new"]
    assert descriptions(Todo) == ["work"]
    assert restored.summary() == "2 rows back"


def test_an_edit_is_taken_back_field_by_field(create_todo):
    todo = create_todo("before")
    history = started_history()

    todo.description = "after"
    todo.due = datetime(2030, 1, 1)
    todo.save()

    history.record()
    restored = history.undo()

    assert restored is not None
    assert restored.changed == [f"Todo_{todo.id}"]
    assert restored.summary() == "1 row changed"

    assert todo.description == "before"
    assert todo.due is None


def test_a_deletion_is_taken_back(create_project):
    project = create_project("doomed")
    todo = project.add_todo()
    todo.description = "work"
    todo.save()

    history = started_history()
    project.drop()

    assert Project.all() == []

    history.record()
    history.undo()

    assert descriptions(Project) == ["doomed"]
    assert descriptions(Todo) == ["work"]


def test_binning_a_project_is_taken_back_whole(create_project):
    """
    One key files every task elsewhere and drops the row; one key puts it back

    The change nothing could write an inverse for by hand: what the todos are
    handed is worked out from a tree that no longer exists by the time the
    undo runs.
    """

    project = create_project("dropped")
    todo = project.add_todo()
    todo.description = "orphaned work"
    todo.save()

    history = started_history()
    move_project_to_bin(project)

    assert Project.all() == []
    assert Todo.all()[0].is_binned

    history.record()
    history.undo()

    revived = Project.all()[0]
    recovered = Todo.all()[0]

    assert revived.description == "dropped"
    assert not recovered.is_binned
    assert recovered.origin_path == ""
    assert recovered.parent_project_id == revived.id


def test_the_fields_a_validator_keeps_in_step_are_put_back_as_they_were(
    create_todo,
):
    """
    A restore writes the rows, not the models

    Ticking a todo off dates it, through a validator hung off the field. Put
    back through the models, the undo would set `pending` and have the
    validator clear the very date it was restoring.
    """

    todo = create_todo("work")
    todo.toggle_complete()

    completed_at = todo.completed_at
    assert completed_at is not None

    history = started_history()

    todo.toggle_complete()
    assert todo.completed_at is None

    history.record()
    history.undo()

    assert todo.pending == False
    assert todo.completed_at == completed_at


def test_the_root_project_is_never_part_of_a_change(create_project):
    """
    The peg the tree hangs off is not a row an undo can pull out from under it
    """

    history = started_history()
    create_project("first")
    history.record()
    history.undo()

    root = Project._get_or_create_root()

    assert root.id is not None
    assert root.is_root


def test_a_step_is_not_itself_a_change_to_be_recorded(create_project):
    history = started_history()
    create_project("new")
    history.record()

    history.undo()

    # The undo committed, but where it arrived is the state the next key is
    # measured against rather than a change of its own
    assert not history.record()
    assert not history._undo
    assert history._redo


def test_a_new_change_closes_off_the_way_forward(create_project):
    history = started_history()
    create_project("first")
    history.record()
    history.undo()

    assert history._redo

    create_project("second")
    history.record()

    assert not history._redo


def test_only_so_many_changes_are_kept(create_project):
    history = started_history()

    for index in range(MAX_DEPTH + 5):
        create_project(f"project {index}")
        history.record()

    assert len(history._undo) == MAX_DEPTH


def test_the_revision_counter_moves_with_the_commits(create_project):
    before = manager.revision
    create_project("one")

    assert manager.revision > before


# --- notes and the history -------------------------------------------------
#
# Notes sit outside undo, for the reasons in `history.NOTE`. What that must
# never mean is a note being destroyed by a key pressed somewhere else, so the
# two ways that could happen are pinned down here.


def test_undoing_an_edit_leaves_the_note_alone(create_project):
    """
    The row is put back by being rewritten, and the note must survive it

    The snapshot the row comes back from never held the note, so a rewrite
    that took the snapshot at its word would blank it.
    """

    project = create_project("project")
    todo = Todo(description="before", parent_project=project, note="keep me")
    todo.save()

    history = started_history()

    todo.description = "after"
    todo.save()
    assert history.record()

    history.undo()

    (restored,) = Todo.all()
    assert restored.description == "before"
    assert restored.note == "keep me"


def test_undoing_a_deletion_brings_the_note_back(create_project):
    """
    A deleted row's note cannot be read back off the row, so it is taken down
    as the row goes
    """

    project = create_project("project")
    todo = Todo(description="doomed", parent_project=project, note="precious")
    todo.save()

    history = started_history()

    todo.drop()
    assert history.record()
    assert Todo.all() == []

    history.undo()

    (restored,) = Todo.all()
    assert restored.description == "doomed"
    assert restored.note == "precious"


def test_a_note_carried_off_by_its_project_comes_back_with_it(create_project):
    """The same, for a todo deleted by the project it was filed in going"""

    project = create_project("project")
    todo = Todo(description="step", parent_project=project, note="precious")
    todo.save()

    history = started_history()

    project.drop()
    assert history.record()
    assert Todo.all() == []

    history.undo()

    (restored,) = Todo.all()
    assert restored.note == "precious"


def test_redo_of_a_deletion_can_be_undone_again(create_project):
    """The note has to survive the whole way round, not just the first undo"""

    project = create_project("project")
    todo = Todo(description="doomed", parent_project=project, note="precious")
    todo.save()

    history = started_history()

    todo.drop()
    history.record()

    history.undo()
    assert Todo.all()[0].note == "precious"

    history.redo()
    assert Todo.all() == []

    history.undo()
    assert Todo.all()[0].note == "precious"


def test_a_note_edit_is_not_a_change_to_take_back(create_project):
    """
    The cost of keeping notes out of the snapshot, written down on purpose

    Typing into a note records nothing, so `ctrl+z` in the panes steps over
    it to whatever was changed before. The note window has its own undo on
    the same key, which is where the typing happens.
    """

    project = create_project("project")
    todo = Todo(description="task", parent_project=project, note="first")
    todo.save()

    history = started_history()

    todo.note = "second"
    todo.save()

    assert not history.record()
    assert not history._undo
    assert Todo.all()[0].note == "second"


def test_a_note_written_beside_a_real_change_stays_written(create_project):
    """
    A change that is taken back does not drag the note back with it
    """

    project = create_project("project")
    todo = Todo(description="before", parent_project=project, note="old note")
    todo.save()

    history = started_history()

    todo.description = "after"
    todo.note = "new note"
    todo.save()
    assert history.record()

    history.undo()

    (restored,) = Todo.all()
    assert restored.description == "before"
    # The description came back; the note did not, and was not lost either
    assert restored.note == "new note"


def test_the_snapshot_does_not_carry_notes(create_project):
    """What the whole thing is for: the history never holds the note text"""

    from todooit.api.history import _capture

    project = create_project("project")
    Todo(description="task", parent_project=project, note="x" * 5000).save()

    snapshot = _capture()
    (row,) = snapshot["todo"].values()

    assert "note" not in row
