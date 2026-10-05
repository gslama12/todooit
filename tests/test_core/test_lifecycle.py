"""
The todo lifecycle: completing, reopening and advancing

Scenarios use two families: "Garden season", a plain task with a
step that recurs on its own, and "Weekly review", a recurring task with a
checklist under it.
"""

from datetime import datetime, timedelta

import pytest
from sqlalchemy import update

from todooit.api import Cadence, Todo, lifecycle, manager, move_todo_to_bin
from tests.test_core.core_base import *  # noqa: F401,F403

MONDAY = datetime(2026, 10, 5, 9, 0)
TUESDAY_NEXT_WEEK = datetime(2026, 10, 13, 9, 0)


def garden_season(project) -> Todo:
    """ "Garden season" with "Water plants" recurring every 3 days, and "Buy seeds" """

    parent = project.add_todo()
    parent.description = "Garden season"
    parent.save()

    water = parent.add_todo()
    water.description = "Water plants"
    water.scheduled = MONDAY
    water.recurrence = Cadence(3, "days")
    water.save()

    seeds = parent.add_todo()
    seeds.description = "Buy seeds"
    seeds.save()

    return parent


def weekly_review(project) -> Todo:
    """ "Weekly review" every week from Monday, with a two-item checklist"""

    parent = project.add_todo()
    parent.description = "Weekly review"
    parent.scheduled = MONDAY
    parent.recurrence = Cadence(1, "weeks")
    parent.save()

    for description in ("Clear the inbox", "Plan next week"):
        step = parent.add_todo()
        step.description = description
        step.save()

    return parent


def steps_of(parent: Todo) -> dict:
    return {step.description: step for step in parent.descendants}


# ------------------------------------------------------------------
# Completion ends the family: completing a non-recurring todo completes its whole family and
# ends every recurrence inside it
# ------------------------------------------------------------------


def test_completing_a_plain_todo_completes_its_whole_family(create_project):
    garden = garden_season(create_project())
    steps = steps_of(garden)

    lifecycle.complete(garden)

    assert garden.is_completed
    assert steps["Water plants"].is_completed
    assert steps["Buy seeds"].is_completed


def test_completing_a_plain_todo_ends_every_recurrence_inside_it(create_project):
    """Once the season is over, watering doesn't come back"""

    garden = garden_season(create_project())
    water = steps_of(garden)["Water plants"]

    lifecycle.complete(garden)

    assert water.recurrence is None
    assert water.scheduled == MONDAY


def test_a_family_completed_together_shares_one_completion_moment(create_project):
    garden = garden_season(create_project())
    lifecycle.complete(garden)

    moments = {node.completed_at for node in garden.family}

    assert len(moments) == 1
    assert None not in moments



def test_completing_every_step_leaves_the_parent_to_be_completed(create_project):
    """Finishing every step of a task is not finishing the task"""

    garden = garden_season(create_project())

    for step in garden.todos:
        lifecycle.complete(step)

    assert garden.is_pending


def test_a_new_step_leaves_the_completed_ones_alone(create_project):
    """Writing a step into a task is not reopening the task"""

    garden = garden_season(create_project())
    seeds = steps_of(garden)["Buy seeds"]
    lifecycle.complete(seeds)

    fresh = garden.add_todo()
    fresh.save()

    assert seeds.is_completed
    assert fresh.is_pending
    assert garden.is_pending

# ------------------------------------------------------------------
# A recurring todo advances: completing a recurring todo advances it, reopens its family and
# moves steps scheduled before the new date onto it
# ------------------------------------------------------------------


def test_completing_a_recurring_todo_advances_it(create_project):
    review = weekly_review(create_project())

    lifecycle.complete(review)

    assert review.is_pending
    assert review.completed_at is None
    assert review.scheduled == MONDAY + timedelta(weeks=1)
    assert review.recurrence == Cadence(1, "weeks")


def test_advancing_reopens_the_whole_checklist(create_project):
    """The review comes round next week with nothing ticked in it"""

    review = weekly_review(create_project())
    inbox = steps_of(review)["Clear the inbox"]
    later = inbox.add_todo()
    later.description = "Archive newsletters"
    later.save()

    lifecycle.complete(inbox)
    assert inbox.is_completed and later.is_completed

    lifecycle.complete(review)

    for step in review.descendants:
        assert step.is_pending, step.description
        assert step.completed_at is None, step.description


def test_advancing_moves_steps_planned_before_the_new_date_onto_it(create_project):
    review = weekly_review(create_project())

    lifecycle.complete(review)

    for step in review.descendants:
        assert step.scheduled == MONDAY + timedelta(weeks=1), step.description


def test_a_recurring_todo_with_no_date_advances_from_now(create_project):
    todo = create_project().add_todo()
    todo.recurrence = Cadence(1, "days")
    todo.save()

    before = datetime.now()
    lifecycle.complete(todo)

    assert todo.is_pending
    assert todo.scheduled is not None
    assert todo.scheduled >= before + timedelta(days=1)


def test_only_completing_advances_a_recurring_todo(create_project):
    """Renaming or reprioritising the review leaves it on its day"""

    review = weekly_review(create_project())

    review.set_priority(3)
    review.description = "Weekly review (long)"
    review.save()

    assert review.scheduled == MONDAY
    assert review.is_pending



def test_advancing_leaves_steps_planned_after_the_new_date_alone(create_project):
    review = weekly_review(create_project())
    plan = steps_of(review)["Plan next week"]
    plan.scheduled = TUESDAY_NEXT_WEEK
    plan.save()

    lifecycle.complete(review)

    assert review.scheduled == MONDAY + timedelta(weeks=1)
    assert plan.scheduled == TUESDAY_NEXT_WEEK



# ------------------------------------------------------------------
# A step advances on its own: a step with no recurring ancestor advances on its own
# ------------------------------------------------------------------


def test_a_recurring_step_advances_on_its_own(create_project):
    garden = garden_season(create_project())
    steps = steps_of(garden)
    water = steps["Water plants"]

    outcome = lifecycle.complete(water)

    assert water.is_pending
    assert water.scheduled == MONDAY + timedelta(days=3)
    assert outcome.advanced_to == water.scheduled
    assert garden.is_pending
    assert steps["Buy seeds"].is_pending


def test_a_recurring_step_that_advances_reopens_its_own_steps(create_project):
    garden = garden_season(create_project())
    water = steps_of(garden)["Water plants"]
    beds = water.add_todo()
    beds.description = "Raised beds"
    beds.save()
    lifecycle.complete(beds)

    lifecycle.complete(water)

    assert beds.is_pending
    assert beds.completed_at is None


def test_a_step_of_a_recurring_checklist_simply_completes(create_project):
    """Story 12: it comes back when the review does, not on its own"""

    review = weekly_review(create_project())
    inbox = steps_of(review)["Clear the inbox"]

    outcome = lifecycle.complete(inbox)

    assert inbox.is_completed
    assert not outcome.advanced
    assert review.is_pending
    assert review.scheduled == MONDAY


# ------------------------------------------------------------------
# Reopening
# ------------------------------------------------------------------


def test_reopening_a_step_reopens_all_its_ancestors(create_project):
    garden = garden_season(create_project())
    seeds = steps_of(garden)["Buy seeds"]
    packet = seeds.add_todo()
    packet.description = "Tomato seeds"
    packet.save()

    lifecycle.complete(garden)
    lifecycle.reopen(packet)

    assert packet.is_pending
    assert seeds.is_pending
    assert garden.is_pending
    assert seeds.completed_at is None
    assert garden.completed_at is None


def test_reopening_a_step_leaves_its_completed_siblings_alone(create_project):
    garden = garden_season(create_project())
    steps = steps_of(garden)

    lifecycle.complete(garden)
    lifecycle.reopen(steps["Buy seeds"])

    assert steps["Water plants"].is_completed


def test_reopening_a_todo_reopens_its_whole_family(create_project):
    garden = garden_season(create_project())
    seeds = steps_of(garden)["Buy seeds"]
    packet = seeds.add_todo()
    packet.save()

    lifecycle.complete(garden)
    lifecycle.reopen(garden)

    for node in garden.family:
        assert node.is_pending, node.description
        assert node.completed_at is None, node.description


def test_reopening_restores_nothing_the_completion_removed(create_project):
    """Reopening restores nothing: watering stays ended; undo is the way back from a mistaken completion"""

    garden = garden_season(create_project())
    water = steps_of(garden)["Water plants"]

    lifecycle.complete(garden)
    lifecycle.reopen(garden)

    assert water.is_pending
    assert water.recurrence is None
    assert water.scheduled == MONDAY

# ------------------------------------------------------------------
# What an operation reports back
# ------------------------------------------------------------------


def test_an_advance_reports_the_new_date(create_project):
    review = weekly_review(create_project())

    outcome = lifecycle.complete(review)

    assert outcome.advanced
    assert outcome.advanced_to == datetime(2026, 10, 12, 9, 0)
    assert outcome.summary().startswith("advanced to Mon 12 Oct")


def test_an_advance_reports_the_steps_it_moved(create_project):
    review = weekly_review(create_project())

    outcome = lifecycle.complete(review)

    assert {o.todo.description for o in outcome.overrides} == {
        "Clear the inbox",
        "Plan next week",
    }
    assert outcome.summary() == "advanced to Mon 12 Oct, 2 steps moved with it"


def test_a_plain_completion_reports_the_recurrences_it_ended(create_project):
    garden = garden_season(create_project())

    outcome = lifecycle.complete(garden)

    assert not outcome.advanced
    assert [o.todo.description for o in outcome.overrides] == ["Water plants"]
    assert outcome.summary() == "recurrence ended on 1 step"


def test_a_completion_with_nothing_to_report_says_nothing(create_project):
    todo = create_project().add_todo()

    outcome = lifecycle.complete(todo)

    assert not outcome
    assert outcome.summary() == ""




def test_toggling_picks_complete_or_reopen_from_the_state(create_project):
    garden = garden_season(create_project())

    completed = garden.toggle_complete()
    assert garden.is_completed
    assert completed.summary() == "recurrence ended on 1 step"

    garden.toggle_complete()
    assert all(node.is_pending for node in garden.family)


def test_toggling_a_recurring_todo_advances_it(create_project):
    review = weekly_review(create_project())

    outcome = review.toggle_complete()

    assert outcome.advanced
    assert review.is_pending

# ------------------------------------------------------------------
# Regression: an unrelated edit of a completed parent never touches its
# steps (it used to advance their recurrences again on every save)
# ------------------------------------------------------------------


def completed_garden_with_a_legacy_recurring_step(project) -> Todo:
    """
    A completed "Garden season" whose "Water plants" still recurs

    Completion ending the family no longer leaves a family like this; databases from before it do.
    Written past the model so no rule gets a say in the setup.
    """

    garden = garden_season(project)
    lifecycle.complete(garden)
    water = steps_of(garden)["Water plants"]

    manager.session.execute(
        update(Todo).where(Todo.id == water.id).values(recurrence=Cadence(3, "days"))
    )
    manager.commit()

    return garden


def _step_state(parent: Todo) -> list:
    return [
        (s.description, s.pending, s.completed_at, s.scheduled, s.recurrence)
        for s in parent.descendants
    ]


@pytest.mark.parametrize(
    "edit",
    [
        lambda garden: garden.set_priority(2),
        lambda garden: garden.shift_down(),
        move_todo_to_bin,
    ],
    ids=["priority", "position", "bin"],
)
def test_editing_a_completed_parent_leaves_its_steps_alone(create_project, edit):
    project = create_project()
    garden = completed_garden_with_a_legacy_recurring_step(project)
    other = project.add_todo()
    other.save()
    before = _step_state(garden)

    edit(garden)
    manager.session.expire_all()

    assert _step_state(garden) == before


# ------------------------------------------------------------------
# The floor: a parent's scheduled date is a floor for its steps
# ------------------------------------------------------------------

WEDNESDAY = datetime(2026, 10, 7, 9, 0)
FRIDAY = datetime(2026, 10, 9, 9, 0)


def tax_return(project) -> Todo:
    """ "Tax return" with "Collect receipts" (and its "Scan receipts") and "File online" """

    parent = project.add_todo()
    parent.description = "Tax return"
    parent.save()

    receipts = parent.add_todo()
    receipts.description = "Collect receipts"
    receipts.save()

    scan = receipts.add_todo()
    scan.description = "Scan receipts"
    scan.save()

    filing = parent.add_todo()
    filing.description = "File online"
    filing.save()

    return parent


def test_scheduling_a_parent_moves_its_unscheduled_steps_onto_it(create_project):
    """The floor, story 20: at every depth"""

    tax = tax_return(create_project())

    lifecycle.schedule(tax, WEDNESDAY)

    assert tax.scheduled == WEDNESDAY
    for step in tax.descendants:
        assert step.scheduled == WEDNESDAY, step.description


def test_scheduling_a_parent_leaves_steps_planned_later_alone(create_project):
    """The floor, story 21: steps may be spread over several days"""

    tax = tax_return(create_project())
    steps = steps_of(tax)
    lifecycle.schedule(steps["Collect receipts"], MONDAY)
    lifecycle.schedule(steps["File online"], FRIDAY)

    outcome = lifecycle.schedule(tax, WEDNESDAY)

    assert steps["Collect receipts"].scheduled == WEDNESDAY
    assert steps["Scan receipts"].scheduled == WEDNESDAY
    assert steps["File online"].scheduled == FRIDAY
    assert {o.todo.description for o in outcome.overrides} == {
        "Collect receipts",
        "Scan receipts",
    }
    assert outcome.summary() == "2 steps moved with it"


def test_a_step_may_be_scheduled_later_than_its_parent(create_project):
    """A step may be later, story 22"""

    tax = tax_return(create_project())
    lifecycle.schedule(tax, MONDAY)
    receipts = steps_of(tax)["Collect receipts"]

    outcome = lifecycle.schedule(receipts, FRIDAY)

    assert receipts.scheduled == FRIDAY
    assert tax.scheduled == MONDAY
    assert steps_of(tax)["File online"].scheduled == MONDAY
    # Only its own step follows it, as the floor says
    assert [o.todo.description for o in outcome.overrides] == ["Scan receipts"]


def test_scheduling_a_step_before_its_parent_pulls_the_parent_back(create_project):
    """An early step pulls its ancestors back, stories 23-24: the other steps stay put"""

    tax = tax_return(create_project())
    lifecycle.schedule(tax, WEDNESDAY)
    steps = steps_of(tax)
    lifecycle.schedule(steps["Scan receipts"], FRIDAY)

    outcome = lifecycle.schedule(steps["Collect receipts"], MONDAY)

    assert steps["Collect receipts"].scheduled == MONDAY
    assert tax.scheduled == MONDAY
    assert steps["File online"].scheduled == WEDNESDAY
    assert steps["Scan receipts"].scheduled == FRIDAY
    assert outcome.summary() == "its parent moved back to Mon 5 Oct"


def test_pulling_back_reaches_every_ancestor_still_later(create_project):
    """An early step pulls its ancestors back, multi-level: "Scan receipts" pulls "Collect receipts" and "Tax return" """

    tax = tax_return(create_project())
    steps = steps_of(tax)
    lifecycle.schedule(tax, WEDNESDAY)
    lifecycle.schedule(steps["Collect receipts"], FRIDAY)

    outcome = lifecycle.schedule(steps["Scan receipts"], MONDAY)

    assert steps["Collect receipts"].scheduled == MONDAY
    assert tax.scheduled == MONDAY
    assert steps["File online"].scheduled == WEDNESDAY
    assert outcome.summary() == "2 ancestors moved back to Mon 5 Oct"


def test_pulling_back_stops_at_ancestors_already_earlier(create_project):
    tax = tax_return(create_project())
    steps = steps_of(tax)
    lifecycle.schedule(tax, MONDAY)
    lifecycle.schedule(steps["Collect receipts"], FRIDAY)

    lifecycle.schedule(steps["Scan receipts"], WEDNESDAY)

    assert steps["Collect receipts"].scheduled == WEDNESDAY
    assert tax.scheduled == MONDAY


def test_clearing_a_parents_date_clears_the_steps_on_it(create_project):
    """Clearing a parent's date clears the steps that followed it; dated ones stay"""

    tax = tax_return(create_project())
    steps = steps_of(tax)
    lifecycle.schedule(tax, MONDAY)
    lifecycle.schedule(steps["File online"], FRIDAY)

    outcome = lifecycle.schedule(tax, None)

    assert tax.scheduled is None
    assert steps["Collect receipts"].scheduled is None
    assert steps["Scan receipts"].scheduled is None
    assert steps["File online"].scheduled == FRIDAY
    assert outcome.summary() == "2 steps unscheduled"


def test_clearing_a_steps_date_under_a_scheduled_parent_gives_it_the_parents(
    create_project,
):
    """An empty step date follows the parent, story 27: an empty step date means "follow the parent" """

    tax = tax_return(create_project())
    receipts = steps_of(tax)["Collect receipts"]
    lifecycle.schedule(tax, MONDAY)
    lifecycle.schedule(receipts, FRIDAY)

    lifecycle.schedule(receipts, None)

    assert receipts.scheduled == MONDAY


def test_clearing_a_steps_date_under_an_unscheduled_parent_clears_it(create_project):
    tax = tax_return(create_project())
    receipts = steps_of(tax)["Collect receipts"]
    lifecycle.schedule(receipts, FRIDAY)

    lifecycle.schedule(receipts, None)

    assert receipts.scheduled is None


def test_a_recurring_step_advancing_leaves_its_parents_date_alone(create_project):
    """A step may be later, story 25: the parent no longer drops out of Today"""

    garden = garden_season(create_project())
    water = steps_of(garden)["Water plants"]
    lifecycle.schedule(garden, MONDAY)

    lifecycle.complete(water)

    assert water.scheduled == MONDAY + timedelta(days=3)
    assert garden.scheduled == MONDAY


def test_a_new_step_starts_on_its_parents_date(create_project):
    """Nothing arrives undated inside work that is already planned (an empty step date follows the parent)"""

    tax = tax_return(create_project())
    lifecycle.schedule(tax, WEDNESDAY)
    receipts = steps_of(tax)["Collect receipts"]

    assert tax.add_todo().scheduled == WEDNESDAY
    assert receipts.add_sibling().scheduled == WEDNESDAY


# ------------------------------------------------------------------
# The ceiling: a parent's due date is a ceiling for its steps
# ------------------------------------------------------------------


def test_a_parents_due_date_moves_its_undated_steps_onto_it(create_project):
    """The ceiling, story 28: at every depth"""

    tax = tax_return(create_project())

    lifecycle.set_due(tax, FRIDAY)

    assert tax.due == FRIDAY
    for step in tax.descendants:
        assert step.due == FRIDAY, step.description


def test_a_parents_due_date_lowers_later_steps_and_leaves_earlier_ones(
    create_project,
):
    """The ceiling, stories 28-29: intermediate deadlines survive"""

    tax = tax_return(create_project())
    steps = steps_of(tax)
    lifecycle.set_due(steps["Collect receipts"], MONDAY)
    lifecycle.set_due(steps["File online"], TUESDAY_NEXT_WEEK)

    outcome = lifecycle.set_due(tax, FRIDAY)

    assert steps["Collect receipts"].due == MONDAY
    assert steps["Scan receipts"].due == MONDAY
    assert steps["File online"].due == FRIDAY
    assert [o.todo.description for o in outcome.overrides] == ["File online"]
    assert outcome.summary() == "1 step now due Fri 9 Oct"


def test_a_parents_due_date_ends_the_recurrence_of_its_steps(create_project):
    """The ceiling with no recurrence under a deadline, story 30: a deadline-bound task has no repeating work"""

    garden = garden_season(create_project())
    water = steps_of(garden)["Water plants"]

    outcome = lifecycle.set_due(garden, FRIDAY)

    assert water.recurrence is None
    assert water.due == FRIDAY
    assert water.scheduled == MONDAY
    assert outcome.summary() == "recurrence ended on 1 step, 2 steps now due Fri 9 Oct"


def test_a_step_due_after_its_parent_is_refused(create_project):
    """Never due after the parent, story 31: deadlines never move silently"""

    tax = tax_return(create_project())
    lifecycle.set_due(tax, FRIDAY)
    filing = steps_of(tax)["File online"]

    with pytest.raises(lifecycle.Refusal) as refusal:
        lifecycle.set_due(filing, TUESDAY_NEXT_WEEK)

    assert str(refusal.value) == "Can't be due after its parent's due date, Fri 9 Oct"


def test_a_refused_change_changes_nothing(create_project):
    """Not even in memory, waiting for the next commit to write it"""

    tax = tax_return(create_project())
    lifecycle.set_due(tax, FRIDAY)
    receipts = steps_of(tax)["Collect receipts"]

    with pytest.raises(lifecycle.Refusal):
        lifecycle.set_due(receipts, TUESDAY_NEXT_WEEK)

    manager.commit()
    manager.session.expire_all()

    assert tax.due == FRIDAY
    for step in tax.descendants:
        assert step.due == FRIDAY, step.description


def test_clearing_a_parents_due_date_clears_the_steps_on_it(create_project):
    """Clearing a parent's deadline clears the steps that followed it; dated ones stay"""

    tax = tax_return(create_project())
    steps = steps_of(tax)
    lifecycle.set_due(tax, FRIDAY)
    lifecycle.set_due(steps["File online"], WEDNESDAY)

    outcome = lifecycle.set_due(tax, None)

    assert tax.due is None
    assert steps["Collect receipts"].due is None
    assert steps["Scan receipts"].due is None
    assert steps["File online"].due == WEDNESDAY
    assert outcome.summary() == "2 steps no longer due"


def test_clearing_a_steps_due_date_under_a_parent_with_one_gives_it_the_parents(
    create_project,
):
    """An empty step deadline is the parent's, story 33: an empty step deadline means "the task's deadline" """

    tax = tax_return(create_project())
    receipts = steps_of(tax)["Collect receipts"]
    lifecycle.set_due(tax, FRIDAY)
    lifecycle.set_due(receipts, MONDAY)

    lifecycle.set_due(receipts, None)

    assert receipts.due == FRIDAY


def test_clearing_a_steps_due_date_under_a_parent_without_one_clears_it(
    create_project,
):
    tax = tax_return(create_project())
    receipts = steps_of(tax)["Collect receipts"]
    lifecycle.set_due(receipts, MONDAY)

    lifecycle.set_due(receipts, None)

    assert receipts.due is None


def test_a_due_date_on_a_recurring_todo_is_refused(create_project):
    """No due date on a recurring todo, story 19: a recurring todo is planned by its scheduled date"""

    review = weekly_review(create_project())

    with pytest.raises(lifecycle.Refusal) as refusal:
        lifecycle.set_due(review, FRIDAY)

    assert str(refusal.value) == (
        "A recurring todo has no due date; set its scheduled date instead"
    )
    assert review.due is None
    assert review.recurrence == Cadence(1, "weeks")


# ------------------------------------------------------------------
# A step on its parent's date follows it: changing or clearing a parent's
# date takes every step holding exactly the old date along; steps with a
# date of their own stay
# ------------------------------------------------------------------


def test_moving_a_parent_earlier_takes_the_steps_on_its_date_along(create_project):
    tax = tax_return(create_project())
    steps = steps_of(tax)
    lifecycle.schedule(tax, WEDNESDAY)
    lifecycle.schedule(steps["File online"], FRIDAY)

    lifecycle.schedule(tax, MONDAY)

    assert steps["Collect receipts"].scheduled == MONDAY
    assert steps["Scan receipts"].scheduled == MONDAY
    assert steps["File online"].scheduled == FRIDAY


def test_moving_a_parent_reports_the_steps_that_followed(create_project):
    tax = tax_return(create_project())
    lifecycle.schedule(tax, WEDNESDAY)

    outcome = lifecycle.schedule(tax, MONDAY)

    assert outcome.summary() == "3 steps moved with it"


def test_moving_a_deadline_later_takes_the_steps_due_with_it_along(create_project):
    tax = tax_return(create_project())
    steps = steps_of(tax)
    lifecycle.set_due(tax, WEDNESDAY)
    lifecycle.set_due(steps["File online"], MONDAY)

    outcome = lifecycle.set_due(tax, FRIDAY)

    assert steps["Collect receipts"].due == FRIDAY
    assert steps["Scan receipts"].due == FRIDAY
    assert steps["File online"].due == MONDAY
    assert outcome.summary() == "2 steps now due Fri 9 Oct"


def test_a_step_on_the_same_day_at_another_time_keeps_its_date(create_project):
    """Following matches the exact date and time, not just the day"""

    tax = tax_return(create_project())
    steps = steps_of(tax)
    lifecycle.schedule(tax, WEDNESDAY)
    lifecycle.schedule(steps["File online"], WEDNESDAY + timedelta(hours=5))

    lifecycle.schedule(tax, MONDAY)

    assert steps["Collect receipts"].scheduled == MONDAY
    assert steps["File online"].scheduled == WEDNESDAY + timedelta(hours=5)


def test_clearing_a_steps_date_takes_its_own_steps_to_the_parents(create_project):
    """An emptied step follows its parent, and the steps that followed it come along"""

    tax = tax_return(create_project())
    steps = steps_of(tax)
    lifecycle.schedule(tax, MONDAY)
    lifecycle.schedule(steps["Collect receipts"], WEDNESDAY)

    outcome = lifecycle.schedule(steps["Collect receipts"], None)

    assert steps["Collect receipts"].scheduled == MONDAY
    assert steps["Scan receipts"].scheduled == MONDAY
    assert outcome.summary() == "1 step moved with it"


def test_steps_with_their_own_date_still_rise_to_a_later_parent(create_project):
    """Following never loosens the floor: an earlier step of its own still moves up"""

    tax = tax_return(create_project())
    steps = steps_of(tax)
    lifecycle.schedule(tax, MONDAY)
    lifecycle.schedule(steps["File online"], WEDNESDAY)

    lifecycle.schedule(tax, FRIDAY)

    assert steps["Collect receipts"].scheduled == FRIDAY
    assert steps["File online"].scheduled == FRIDAY


def test_a_followed_date_is_stored(create_project):
    tax = tax_return(create_project())
    lifecycle.set_due(tax, WEDNESDAY)

    lifecycle.set_due(tax, None)
    manager.session.expire_all()

    for step in tax.descendants:
        assert step.due is None, step.description


# Recurrence ownership


def test_a_recurrence_wipes_every_recurrence_below_it(create_project):
    """One cadence per line, story 14: only one todo on a line owns the cadence"""

    garden = garden_season(create_project())
    water = steps_of(garden)["Water plants"]
    hose = water.add_todo()
    hose.description = "Coil the hose"
    hose.recurrence = Cadence(1, "days")
    hose.save()

    lifecycle.set_recurrence(garden, Cadence(1, "weeks"))

    assert garden.recurrence == Cadence(1, "weeks")
    assert water.recurrence is None
    assert hose.recurrence is None


def test_wiped_recurrences_are_reported(create_project):
    """Story 15: the status bar says which recurrences below were wiped"""

    garden = garden_season(create_project())
    lifecycle.schedule(garden, MONDAY)
    water = steps_of(garden)["Water plants"]

    outcome = lifecycle.set_recurrence(garden, Cadence(1, "weeks"))

    assert [(o.todo, o.what) for o in outcome.overrides] == [
        (water, lifecycle.Change.ENDED)
    ]
    assert outcome.summary() == "recurrence ended on 1 step"


def test_a_recurrence_with_nothing_below_says_nothing(create_project):
    todo = create_project().add_todo()

    assert not lifecycle.set_recurrence(todo, Cadence(2, "days"))


def test_a_recurrence_under_a_recurring_grandparent_is_refused(create_project):
    """One cadence per line, story 16: "Weekly review" -> "Admin" -> "Pay rent" has one cadence"""

    review = weekly_review(create_project())
    admin = review.add_todo()
    admin.description = "Admin"
    admin.save()
    rent = admin.add_todo()
    rent.description = "Pay rent"
    rent.save()

    with pytest.raises(lifecycle.Refusal) as refusal:
        lifecycle.set_recurrence(rent, Cadence(4, "weeks"))

    assert str(refusal.value) == (
        "Can't recur: its ancestor \"Weekly review\" already recurs"
    )
    manager.session.expire_all()
    assert rent.recurrence is None


def test_a_recurrence_under_a_due_dated_ancestor_is_refused(create_project):
    """No recurrence under a deadline, story 17: a deadline-bound task never contains repeating work"""

    tax = tax_return(create_project())
    lifecycle.set_due(tax, FRIDAY)
    scan = steps_of(tax)["Scan receipts"]
    manager.session.commit()

    with pytest.raises(lifecycle.Refusal) as refusal:
        lifecycle.set_recurrence(scan, Cadence(1, "days"))

    # The nearest one: the deadline reached "Collect receipts" too (the ceiling)
    assert str(refusal.value) == (
        "Can't recur: its ancestor \"Collect receipts\" is due Fri 9 Oct"
    )
    manager.session.expire_all()
    assert scan.recurrence is None


def test_a_recurrence_turns_the_due_date_into_the_scheduled_date(create_project):
    """No due date on a recurring todo, story 18: a recurring todo is a cadence, not a deadline"""

    todo = create_project().add_todo()
    lifecycle.set_due(todo, FRIDAY)

    lifecycle.set_recurrence(todo, Cadence(1, "weeks"))

    assert todo.scheduled == FRIDAY
    assert todo.due is None


def test_a_recurrence_keeps_the_scheduled_date_and_drops_the_due_date(
    create_project,
):
    """No due date on a recurring todo: the day it was planned for wins over the deadline"""

    todo = create_project().add_todo()
    lifecycle.schedule(todo, MONDAY)
    lifecycle.set_due(todo, FRIDAY)

    lifecycle.set_recurrence(todo, Cadence(1, "weeks"))

    assert todo.scheduled == MONDAY
    assert todo.due is None


def test_a_recurrence_on_an_undated_todo_starts_it_today(create_project):
    """As before the lifecycle: a cadence needs a first day, and steps join it"""

    garden = garden_season(create_project())
    seeds = steps_of(garden)["Buy seeds"]
    lifecycle.schedule(seeds, None)
    assert garden.scheduled is None and seeds.scheduled is None

    outcome = lifecycle.set_recurrence(garden, Cadence(1, "weeks"))

    today = datetime.now().date()
    assert garden.scheduled is not None and garden.scheduled.date() == today
    assert seeds.scheduled is not None and seeds.scheduled.date() == today
    assert (seeds, lifecycle.Change.MOVED) in [(o.todo, o.what) for o in outcome.overrides]


def test_clearing_a_recurrence_is_never_refused(create_project):
    """Even under a due-dated parent: taking a cadence away breaks no rule"""

    garden = garden_season(create_project())
    water = steps_of(garden)["Water plants"]
    garden.due = FRIDAY  # an old row, from before the rules
    garden.save()

    assert not lifecycle.set_recurrence(water, None)
    assert water.recurrence is None


# ------------------------------------------------------------------
# Becoming a step is fitted, never refused; leaving keeps values
# ------------------------------------------------------------------


def loose_todo(project, description: str, **values) -> Todo:
    """A top-level todo, not yet a step of anything"""

    todo = project.add_todo()
    todo.description = description

    for name, value in values.items():
        setattr(todo, name, value)

    todo.save()
    return todo


def test_a_new_step_inherits_its_parents_due_date(create_project):
    """Story 34: new work starts inside its task's plan"""

    tax = tax_return(create_project())
    lifecycle.set_due(tax, FRIDAY)
    receipts = steps_of(tax)["Collect receipts"]

    assert tax.add_todo().due == FRIDAY
    assert receipts.add_sibling().due == FRIDAY


def test_an_indented_todo_takes_its_new_parents_empty_dates(create_project):
    """Story 35: filling a gap overrides nothing, so there is nothing to tell"""

    project = create_project()
    tax = tax_return(project)
    lifecycle.schedule(tax, WEDNESDAY)
    lifecycle.set_due(tax, FRIDAY)
    forms = loose_todo(project, "Print forms")

    outcome = forms.indent(tax)

    assert forms.parent_todo == tax
    assert forms.scheduled == WEDNESDAY
    assert forms.due == FRIDAY
    assert not outcome


def test_an_indented_todo_is_raised_to_its_new_parents_day(create_project):
    """Story 35: it can't start before its task, and neither can its steps"""

    project = create_project()
    tax = tax_return(project)
    lifecycle.schedule(tax, WEDNESDAY)
    forms = loose_todo(project, "Print forms")
    lifecycle.schedule(forms, MONDAY)
    ink = forms.add_todo()

    outcome = forms.indent(tax)

    assert forms.scheduled == WEDNESDAY
    assert ink.scheduled == WEDNESDAY
    assert outcome.summary() == "moved to Wed 7 Oct, 1 step moved with it"


def test_an_indented_todo_planned_later_keeps_its_day(create_project):
    project = create_project()
    tax = tax_return(project)
    lifecycle.schedule(tax, MONDAY)
    forms = loose_todo(project, "Print forms")
    lifecycle.schedule(forms, FRIDAY)

    outcome = forms.indent(tax)

    assert forms.scheduled == FRIDAY
    assert tax.scheduled == MONDAY
    assert not outcome


def test_an_indented_todo_is_lowered_to_its_new_parents_deadline(create_project):
    """Story 35: it can't be due after its task, and neither can its steps"""

    project = create_project()
    tax = tax_return(project)
    lifecycle.set_due(tax, WEDNESDAY)
    forms = loose_todo(project, "Print forms")
    lifecycle.set_due(forms, FRIDAY)
    ink = forms.add_todo()

    outcome = forms.indent(tax)

    assert forms.due == WEDNESDAY
    assert ink.due == WEDNESDAY
    assert outcome.summary() == "now due Wed 7 Oct, 1 step now due Wed 7 Oct"


def test_an_indented_todo_due_earlier_keeps_its_deadline(create_project):
    project = create_project()
    tax = tax_return(project)
    lifecycle.set_due(tax, FRIDAY)
    forms = loose_todo(project, "Print forms")
    lifecycle.set_due(forms, MONDAY)

    outcome = forms.indent(tax)

    assert forms.due == MONDAY
    assert tax.due == FRIDAY
    assert not outcome


def test_an_indented_todo_stops_recurring_under_a_recurring_ancestor(create_project):
    """Stories 35, 37: one cadence per line is kept by the newcomer giving way, not by a refusal"""

    project = create_project()
    review = weekly_review(project)
    inbox = steps_of(review)["Clear the inbox"]
    stretch = loose_todo(
        project, "Stretch", scheduled=MONDAY, recurrence=Cadence(1, "days")
    )

    outcome = stretch.indent(inbox)

    assert stretch.parent_todo == inbox
    assert stretch.recurrence is None
    assert stretch.scheduled == MONDAY
    assert review.recurrence == Cadence(1, "weeks")
    assert outcome.summary() == "stopped recurring"


def test_an_indented_family_stops_recurring_under_a_due_date(create_project):
    """Stories 35, 37: no recurrence under a deadline for every todo in the family that arrives"""

    project = create_project()
    tax = tax_return(project)
    lifecycle.set_due(tax, FRIDAY)
    garden = garden_season(project)
    water = steps_of(garden)["Water plants"]

    outcome = garden.indent(tax)

    assert water.recurrence is None
    assert water.scheduled == MONDAY
    assert garden.due == FRIDAY
    assert water.due == FRIDAY
    assert outcome.summary() == "recurrence ended on 1 step, 2 steps now due Fri 9 Oct"


def test_a_recurring_todo_indented_under_a_due_date_takes_the_deadline(
    create_project,
):
    """Its recurrence gives way first, so the deadline isn't refused (no due date on a recurring todo)"""

    project = create_project()
    tax = tax_return(project)
    lifecycle.set_due(tax, FRIDAY)
    review = weekly_review(project)

    review.indent(tax)

    assert review.recurrence is None
    assert review.scheduled == MONDAY
    assert review.due == FRIDAY


def test_an_unindented_step_keeps_its_values(create_project):
    """Leaving keeps values, story 39: promoting a step changes nothing else"""

    project = create_project()
    tax = tax_return(project)
    lifecycle.schedule(tax, WEDNESDAY)
    lifecycle.set_due(tax, FRIDAY)
    receipts = steps_of(tax)["Collect receipts"]

    outcome = receipts.unindent()

    assert receipts.parent_project == project
    assert receipts.scheduled == WEDNESDAY
    assert receipts.due == FRIDAY
    assert tax.scheduled == WEDNESDAY
    assert tax.due == FRIDAY
    assert not outcome


def test_a_step_moved_to_a_project_keeps_its_values(create_project):
    """Leaving keeps values, story 39"""

    tax = tax_return(create_project())
    lifecycle.schedule(tax, WEDNESDAY)
    lifecycle.set_due(tax, FRIDAY)
    receipts = steps_of(tax)["Collect receipts"]
    elsewhere = create_project()

    outcome = receipts.move_to(elsewhere)

    assert receipts.parent_project == elsewhere
    assert receipts.scheduled == WEDNESDAY
    assert receipts.due == FRIDAY
    assert not outcome


def test_placing_writes_everything_in_one_commit(create_project):
    """Story 52: one key press, one row diff, one undo"""

    project = create_project()
    tax = tax_return(project)
    lifecycle.set_due(tax, WEDNESDAY)
    forms = loose_todo(project, "Print forms", recurrence=Cadence(1, "days"))
    before = manager.revision

    forms.indent(tax)

    assert manager.revision == before + 1


# ------------------------------------------------------------------
# A completed step keeps its dates: a parent's new date, floor or ceiling
# passes it by, and the rules catch up with it when it is reopened
# ------------------------------------------------------------------

SATURDAY = datetime(2026, 10, 10, 9, 0)


def test_moving_a_parent_leaves_a_completed_step_on_the_old_date(create_project):
    tax = tax_return(create_project())
    steps = steps_of(tax)
    lifecycle.schedule(tax, WEDNESDAY)
    lifecycle.complete(steps["Collect receipts"])

    outcome = lifecycle.schedule(tax, MONDAY)

    assert steps["Collect receipts"].scheduled == WEDNESDAY
    assert steps["Scan receipts"].scheduled == WEDNESDAY
    assert steps["File online"].scheduled == MONDAY
    assert outcome.summary() == "1 step moved with it"


def test_a_later_floor_passes_a_completed_step_by(create_project):
    tax = tax_return(create_project())
    steps = steps_of(tax)
    lifecycle.schedule(tax, MONDAY)
    lifecycle.complete(steps["Collect receipts"])

    lifecycle.schedule(tax, FRIDAY)

    assert steps["Collect receipts"].scheduled == MONDAY
    assert steps["Scan receipts"].scheduled == MONDAY
    assert steps["File online"].scheduled == FRIDAY


def test_moving_a_deadline_leaves_a_completed_step_due_on_the_old_date(create_project):
    tax = tax_return(create_project())
    steps = steps_of(tax)
    lifecycle.set_due(tax, FRIDAY)
    lifecycle.complete(steps["Collect receipts"])

    lifecycle.set_due(tax, WEDNESDAY)

    assert steps["Collect receipts"].due == FRIDAY
    assert steps["Scan receipts"].due == FRIDAY
    assert steps["File online"].due == WEDNESDAY


def test_clearing_a_parents_dates_leaves_a_completed_step_its_own(create_project):
    tax = tax_return(create_project())
    steps = steps_of(tax)
    lifecycle.schedule(tax, MONDAY)
    lifecycle.set_due(tax, FRIDAY)
    lifecycle.complete(steps["File online"])

    lifecycle.schedule(tax, None)
    lifecycle.set_due(tax, None)

    assert steps["File online"].scheduled == MONDAY
    assert steps["File online"].due == FRIDAY
    assert steps["Collect receipts"].scheduled is None
    assert steps["Collect receipts"].due is None


def test_a_reopened_step_rises_to_its_parents_floor(create_project):
    tax = tax_return(create_project())
    steps = steps_of(tax)
    lifecycle.schedule(tax, MONDAY)
    lifecycle.complete(steps["Collect receipts"])
    lifecycle.schedule(tax, FRIDAY)

    outcome = lifecycle.reopen(steps["Collect receipts"])

    assert steps["Collect receipts"].scheduled == FRIDAY
    assert steps["Scan receipts"].scheduled == FRIDAY
    assert outcome.summary() == "moved to Fri 9 Oct, 1 step moved with it"


def test_a_reopened_step_comes_down_to_its_parents_ceiling(create_project):
    tax = tax_return(create_project())
    steps = steps_of(tax)
    lifecycle.set_due(tax, FRIDAY)
    lifecycle.complete(steps["Collect receipts"])
    lifecycle.set_due(tax, WEDNESDAY)

    lifecycle.reopen(steps["Scan receipts"])

    assert steps["Collect receipts"].due == WEDNESDAY
    assert steps["Scan receipts"].due == WEDNESDAY


def test_a_reopened_step_planned_later_keeps_its_day(create_project):
    """Reopening applies the floor, not the parent's date: a later step stays"""

    tax = tax_return(create_project())
    steps = steps_of(tax)
    lifecycle.schedule(tax, MONDAY)
    lifecycle.schedule(steps["File online"], SATURDAY)
    lifecycle.complete(steps["File online"])
    lifecycle.schedule(tax, WEDNESDAY)

    outcome = lifecycle.reopen(steps["File online"])

    assert steps["File online"].scheduled == SATURDAY
    assert not outcome


def test_reopening_leaves_completed_siblings_on_their_dates(create_project):
    tax = tax_return(create_project())
    steps = steps_of(tax)
    lifecycle.schedule(tax, MONDAY)
    lifecycle.complete(steps["Collect receipts"])
    lifecycle.complete(steps["File online"])
    lifecycle.schedule(tax, FRIDAY)

    lifecycle.reopen(steps["File online"])

    assert steps["File online"].scheduled == FRIDAY
    assert steps["Collect receipts"].scheduled == MONDAY


def test_advancing_still_moves_the_completed_checklist_onto_the_new_date(
    create_project,
):
    review = weekly_review(create_project())
    checklist = steps_of(review)
    lifecycle.complete(checklist["Clear the inbox"])

    lifecycle.complete(review)

    assert checklist["Clear the inbox"].is_pending
    assert checklist["Clear the inbox"].scheduled == datetime(2026, 10, 12, 9, 0)
