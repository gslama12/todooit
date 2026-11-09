"""
One refresh signal: after a key press that changed the database, every pane
redraws from the rows that key left different, whatever code made the change
"""

from datetime import datetime

from tests.test_ui.ui_base import (
    boot,
    descriptions,
    press_writing,
    reveal_project,
    run_pilot,
    visible_todos,
)
from todooit.api import Project, Todo
from todooit.ui.tui import Todooit
from todooit.ui.widgets.trees.model_tree import ModelTree


def weekly_review(app: Todooit) -> Todo:
    """ "Weekly review" planned for today, with one step also planned for today"""

    # Filed under the projects pane's own root: on a fresh database that root
    # is only written once something is added to it
    project = app.api.vars.projects_tree.model.add_project()
    project.description = "Home"
    project.save()

    parent = project.add_todo()
    parent.description = "Weekly review"
    parent.save()

    step = parent.add_todo()
    step.description = "Clear the inbox"
    step.save()

    # Planned last: a parent's date is what its steps are fitted to
    parent.scheduled = datetime.now()
    parent.save()

    return parent


async def test_a_todo_written_by_any_key_shows_up_in_today():
    async with run_pilot() as pilot:
        app = await boot(pilot)

        await press_writing(pilot, lambda: weekly_review(app))

        assert "Weekly review" in descriptions(visible_todos(app))


async def test_deleting_a_parent_drops_its_steps_from_every_pane():
    async with run_pilot() as pilot:
        app = await boot(pilot)
        app.api.vars.always_expand_todos = True

        family = []
        await press_writing(pilot, lambda: family.append(weekly_review(app)))
        (parent,) = family
        step = parent.todos[0]
        gone = {parent.uuid, step.uuid}

        # Both the project's own pane and Today have drawn the family
        home = await reveal_project(pilot, parent.parent_project)
        assert descriptions(home) == ["Weekly review", "Clear the inbox"]

        await press_writing(pilot, parent.drop)

        panes = list(app.screen.query(ModelTree))
        assert len(panes) >= 2

        for pane in panes:
            pane.refresh_if_dirty()
            assert not gone & set(pane._renderers), pane.id
            assert not gone & {option.id for option in pane._options}, pane.id


MAPPER_EVENTS = (
    "before_insert",
    "after_insert",
    "before_update",
    "after_update",
    "before_delete",
    "after_delete",
)


def mapper_listeners() -> int:
    """How many database listeners hang off the todo and project tables"""

    return sum(
        len(getattr(model.__mapper__.dispatch, name))
        for model in (Todo, Project)
        for name in MAPPER_EVENTS
    )


async def test_booting_the_main_screen_again_adds_no_listeners():
    """The app doesn't collect listeners the longer (or more often) it runs"""

    counts = []

    for _ in range(2):
        async with run_pilot() as pilot:
            await boot(pilot)
            counts.append(mapper_listeners())

    assert counts[0] == counts[1]


async def test_config_subscribers_still_hear_the_app_events():
    """Only the per-field change events went: the ones config code listens to stay"""

    from todooit.ui.api.event_handlers import subscribe
    from todooit.ui.api.events import ModeChanged, ProjectSelected

    heard = []

    @subscribe(ModeChanged, ProjectSelected)
    def listener(_api, event):
        heard.append(type(event).__name__)
        return ""

    async with run_pilot() as pilot:
        app = await boot(pilot)
        app.api.config_manager.register(listener)

        # Onto the projects pane, then in and out of naming a new project
        await pilot.press("j")
        await pilot.pause()
        await pilot.press("n")
        await pilot.pause()
        await pilot.press("escape")
        await pilot.pause()

    assert "ModeChanged" in heard, heard
    assert "ProjectSelected" in heard


async def test_undo_flashes_the_rows_it_put_back():
    async with run_pilot() as pilot:
        app = await boot(pilot)

        family = []
        await press_writing(pilot, lambda: family.append(weekly_review(app)))
        (parent,) = family
        home = await reveal_project(pilot, parent.parent_project)

        await press_writing(pilot, parent.drop)
        assert descriptions(home) == []

        await pilot.press("u")
        await pilot.pause()

        assert descriptions(home)[0] == "Weekly review"
        assert parent.uuid in home._flashing
