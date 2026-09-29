from datetime import datetime

from textual.pilot import Pilot
from textual.widgets import ContentSwitcher

from todooit.api import COMPLETED, Project, Todo
from todooit.ui.screens.note import NoteScreen
from todooit.ui.screens.search import (
    BINNED,
    DONE,
    EMPTY_NOTE_QUERY,
    EMPTY_QUERY,
    MAX_NOTE_ROWS,
    MAX_ROWS,
    NOTES_TITLE,
    NO_NOTE_MATCHES,
    PANEL_TITLE,
    SearchScreen,
    snippet,
)
from todooit.ui.tui import Todooit
from todooit.ui.widgets.trees.todos_tree import TodosTree
from tests.test_ui.ui_base import run_pilot

ITEMS = ["apple", "apps", "applet", "apricot"]


async def seed(pilot: Pilot) -> Project:
    """
    Fills the database with a project of tasks and shows the panes it

    Written straight to the database rather than typed into the panes: what is
    being tested is finding a task that is somewhere else entirely, and typing
    one in leaves the cursor sitting on it.
    """

    app = pilot.app
    assert isinstance(app, Todooit)

    # Filed under the root the pane itself was built with, rather than under
    # one looked up again: the pane draws what hangs off the object it holds
    project = app.api.vars.projects_tree.model.add_project()
    project.description = "project"
    project.save()

    for item in ITEMS:
        todo = project.add_todo()
        todo.description = item
        todo.save()

    app.api.vars.projects_tree.force_refresh()
    await pilot.pause()

    return project


def visible_todos(app: Todooit) -> TodosTree:
    tree = app.screen.query_one(
        "#todo_switcher", expect_type=ContentSwitcher
    ).visible_content

    assert isinstance(tree, TodosTree)
    return tree


async def open_search(pilot: Pilot) -> SearchScreen:
    await pilot.press("/")
    await pilot.pause()

    screen = pilot.app.screen
    assert isinstance(screen, SearchScreen)

    return screen


async def test_search_narrows_and_orders():
    async with run_pilot() as pilot:
        await seed(pilot)
        screen = await open_search(pilot)

        # Nothing typed yet, so there is nothing to offer
        assert screen._matches == []

        await pilot.press(*list("app"))
        await pilot.pause()

        # Every task starting with what was typed, in alphabetical order:
        # none of them carries a deadline to be told apart by
        assert [match.todo.description for match in screen._matches] == [
            "apple",
            "applet",
            "apps",
        ]

        # A word none of the tasks says, but the project they are in does
        await pilot.press(*(["backspace"] * 3))
        await pilot.press(*list("project"))
        await pilot.pause()

        assert len(screen._matches) == len(ITEMS)

        # And one nobody says at all
        await pilot.press(*list("zzz"))
        await pilot.pause()

        assert screen._matches == []


async def test_search_jumps_to_the_task():
    async with run_pilot() as pilot:
        await seed(pilot)
        await open_search(pilot)

        await pilot.press(*list("app"))
        await pilot.press("down")
        await pilot.pause()

        await pilot.press("enter")
        await pilot.pause()
        await pilot.pause()

        app = pilot.app
        assert isinstance(app, Todooit)
        assert not isinstance(app.screen, SearchScreen)

        todos = visible_todos(app)
        assert todos.current_model.description == "applet"
        assert app.focused is todos


async def test_search_puts_finished_and_binned_last():
    async with run_pilot() as pilot:
        await seed(pilot)

        binned, completed = Todo.all()[0], Todo.all()[1]
        binned.binned_at = datetime.now()
        binned.save()
        completed.toggle_complete()
        completed.save()

        screen = await open_search(pilot)
        await pilot.press(*list("app"))
        await pilot.pause()

        # Everything is still findable; what changes is the block it is in,
        # and the blocks come in one order
        sections = [match.section for match in screen._matches]
        assert sections == sorted(sections)
        assert sections[-2:] == [DONE, BINNED]

        found = {match.todo.description: match.section for match in screen._matches}
        assert found[completed.description] == DONE
        assert found[binned.description] == BINNED


async def test_search_jumps_to_the_pane_a_finished_task_moved_to():
    async with run_pilot() as pilot:
        await seed(pilot)

        completed = Todo.all()[0]
        completed.description = "singular finished thing"
        completed.toggle_complete()
        completed.save()

        await open_search(pilot)
        await pilot.press(*list("singular"))
        await pilot.pause()
        await pilot.press("enter")
        await pilot.pause()
        await pilot.pause()

        app = pilot.app
        assert isinstance(app, Todooit)

        todos = visible_todos(app)
        assert todos.model is COMPLETED
        assert todos.current_model.description == completed.description


async def test_search_scrolls_through_the_matches():
    async with run_pilot() as pilot:
        project = await seed(pilot)

        for index in range(MAX_ROWS + 5):
            todo = project.add_todo()
            todo.description = f"apple number {index}"
            todo.save()

        screen = await open_search(pilot)
        await pilot.press(*list("apple"))
        await pilot.pause()

        assert len(screen._matches) > MAX_ROWS
        assert screen._offset == 0

        # The window stays put until the cursor walks off the end of it
        for _ in range(MAX_ROWS - 1):
            await pilot.press("down")

        await pilot.pause()
        assert screen._offset == 0

        await pilot.press("down")
        await pilot.pause()
        assert screen._offset == 1

        # Back up to the top, taking the window with it
        for _ in range(MAX_ROWS):
            await pilot.press("up")

        await pilot.pause()
        assert (screen._index, screen._offset) == (0, 0)

        # And round the end of the list in one key
        await pilot.press("up")
        await pilot.pause()
        assert screen._index == len(screen._matches) - 1
        assert screen._offset == len(screen._matches) - MAX_ROWS


async def test_search_can_be_cancelled():
    async with run_pilot() as pilot:
        await seed(pilot)
        await open_search(pilot)

        await pilot.press("escape")
        await pilot.pause()

        assert not isinstance(pilot.app.screen, SearchScreen)


# ----------------------------------------------------------------------
# Looking through the notes: a query that starts with `>`
# ----------------------------------------------------------------------

NOTES = {
    "apple": "the reinvoiced amount is wrong",
    "apps": "call the grocer\n- ask about the invoice for march",
    "applet": "nothing to see here",
}


def write_notes(notes=NOTES) -> None:
    for todo in Todo.all():
        if todo.description in notes:
            todo.note = notes[todo.description]
            todo.save()


async def type_note_query(pilot: Pilot, words: str) -> None:
    await pilot.press("greater_than_sign", *list(words))
    await pilot.pause()


def test_snippet_drops_the_line_mark_and_cuts_in_front_of_the_match():
    assert snippet("- ask about the invoice", 16) == "ask about the invoice"
    assert snippet("  1. first", 5) == "first"
    assert snippet("> ## quoted heading", 5) == "quoted heading"

    # A link is shown by its name, the way the note draws it
    assert snippet("see [the doc](https://example.com/x) now", 0) == "see the doc now"

    long = "word " * 20 + "needle at the end"
    cut = snippet(long, long.index("needle"), lead=10)
    assert cut.startswith("…")
    assert "needle at the end" in cut


async def test_the_prefix_looks_in_the_notes_and_nowhere_else():
    async with run_pilot() as pilot:
        await seed(pilot)
        write_notes()
        screen = await open_search(pilot)

        # What the finder offers before anything is typed says the prefix
        # is there
        assert EMPTY_QUERY.endswith("> for notes")
        assert screen.panel.border_title == PANEL_TITLE

        # The notes are not read until they are asked for
        assert screen._notes is None

        await type_note_query(pilot, "")
        assert screen.in_notes
        assert screen.panel.border_title == NOTES_TITLE
        assert screen._results().plain == EMPTY_NOTE_QUERY
        assert screen._matches == []

        # "apple" is a task title and in no note, so nothing answers it
        await pilot.press(*list("apple"))
        await pilot.pause()
        assert screen._matches == []
        assert screen._results().plain == NO_NOTE_MATCHES

        # Taking the prefix away finds it among the tasks again
        await pilot.press(*(["backspace"] * 6))
        await pilot.press(*list("apple"))
        await pilot.pause()
        assert not screen.in_notes
        assert screen.panel.border_title == PANEL_TITLE
        assert screen._matches[0].todo.description == "apple"


async def test_note_matches_rank_a_word_start_first():
    async with run_pilot() as pilot:
        await seed(pilot)
        write_notes()
        screen = await open_search(pilot)

        # "apps" has a word starting with it, "apple" only has it inside
        # "reinvoiced", so it comes second whatever the alphabet says
        await type_note_query(pilot, " invoice")

        assert [match.todo.description for match in screen._matches] == [
            "apps",
            "apple",
        ]

        hit = screen._matches[0].hit
        assert (hit.row, hit.column) == (1, 16)

        # Every word has to be in the note, though not on the same line
        await pilot.press(*list(" grocer"))
        await pilot.pause()
        assert [match.todo.description for match in screen._matches] == ["apps"]


async def test_note_matches_keep_the_blocks():
    async with run_pilot() as pilot:
        await seed(pilot)
        write_notes({"apple": "invoice", "apps": "invoice", "applet": "invoice"})

        done = next(todo for todo in Todo.all() if todo.description == "apple")
        done.toggle_complete()
        done.save()

        screen = await open_search(pilot)
        await type_note_query(pilot, "invoice")

        sections = [match.section for match in screen._matches]
        assert sections == sorted(sections)
        assert screen._matches[-1].todo.description == "apple"
        assert sections[-1] == DONE


async def test_note_matches_take_two_lines_so_fewer_are_shown():
    async with run_pilot() as pilot:
        project = await seed(pilot)

        for index in range(MAX_NOTE_ROWS + 3):
            todo = project.add_todo()
            todo.description = f"task {index}"
            todo.note = "the needle"
            todo.save()

        screen = await open_search(pilot)
        await type_note_query(pilot, "needle")

        assert screen.rows == MAX_NOTE_ROWS < MAX_ROWS

        for _ in range(MAX_NOTE_ROWS):
            await pilot.press("down")

        await pilot.pause()
        assert screen._offset == 1


async def test_picking_a_note_match_opens_the_note_on_its_line():
    async with run_pilot() as pilot:
        await seed(pilot)
        write_notes()
        await open_search(pilot)
        await type_note_query(pilot, "invoice")

        await pilot.press("enter")
        await pilot.pause()
        await pilot.pause()

        app = pilot.app
        assert isinstance(app, Todooit)

        screen = app.screen
        assert isinstance(screen, NoteScreen)
        assert screen.todo.description == "apps"
        assert screen.editor.cursor_location == (1, 16)

        # And behind it, the task has been gone to, so closing the note
        # leaves the cursor on it
        await pilot.press("escape")
        await pilot.pause()

        todos = visible_todos(app)
        assert todos.current_model.description == "apps"
