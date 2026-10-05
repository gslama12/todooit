from datetime import datetime

from todooit.api import Cadence

from tests.test_core.core_base import *  # noqa

# Completing, reopening and advancing are tested against the lifecycle
# module in test_lifecycle.py, as are scheduled dates. What stays here are
# the data-shape rules a todo applies to itself.


def test_recurrence_forces_pending(create_project):
    """Setting a recurrence on a finished todo hands it back as work"""

    p = create_project()
    t = p.add_todo()
    t.toggle_complete()
    assert t.is_completed

    t.recurrence = Cadence(1, "weeks")
    t.save()

    assert t.is_pending


FRIDAY = datetime(2026, 10, 9, 9, 0)
MONDAY = datetime(2026, 10, 5, 9, 0)


def test_a_recurrence_turns_the_deadline_into_the_day_at_once(create_project):
    """No due date on a recurring todo holds the moment it is set, not only once the row is written"""

    t = create_project().add_todo()
    t.due = FRIDAY

    t.recurrence = Cadence(1, "weeks")

    assert t.due is None
    assert t.scheduled == FRIDAY


def test_a_recurrence_keeps_an_existing_day(create_project):
    t = create_project().add_todo()
    t.scheduled = MONDAY
    t.due = FRIDAY

    t.recurrence = Cadence(1, "weeks")

    assert t.due is None
    assert t.scheduled == MONDAY


def test_a_deadline_given_to_a_recurring_todo_becomes_its_day(create_project):
    """Whatever the order its fields are written in"""

    t = create_project().add_todo()
    t.recurrence = Cadence(1, "weeks")

    t.due = FRIDAY

    assert t.due is None
    assert t.scheduled == FRIDAY
