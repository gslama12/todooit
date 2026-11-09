"""
The note's vim keys in a todo's description, edited inline with `e`
"""

from typing import List

import pytest
from rich.style import Style

from tests.test_ui.test_vim_note import note_holding
from tests.test_ui.ui_base import (
    commit_line,
    create_and_move_to_todo,
    descriptions,
    press_writing,
    run_pilot,
)
from todooit.api import Project, Todo
from todooit.ui.screens.note.disp.theme import backdrop_style, target_style
from todooit.ui.slim_cursor import slim_cursor
from todooit.ui.tui import Todooit
from todooit.ui.widgets.inputs.model_inputs import TodoDescription
from todooit.ui.widgets.trees.model_tree import ModelTree
from todooit.vim_engine import MODE_INSERT, MODE_NORMAL, VimEngine


def field(tree: ModelTree) -> TodoDescription:
    component = tree.current._get_component("description")
    assert isinstance(component, TodoDescription)
    return component


def engine(tree: ModelTree) -> VimEngine:
    found = field(tree).engine
    assert found is not None
    return found


def bar_text(app: Todooit) -> str:
    return str(app.bar.render_line(0).text)


async def a_todo(pilot, name: str) -> ModelTree:
    """A todo called `name`, highlighted in its pane, not being edited."""

    tree = await create_and_move_to_todo(pilot)
    await pilot.press("n")
    await commit_line(pilot, name)
    return tree


async def vim_edit(pilot, name: str) -> ModelTree:
    """A todo called `name`, its description open in a vim edit."""

    tree = await a_todo(pilot, name)
    await pilot.press("e")
    await pilot.pause()
    return tree


async def an_empty_todo(pilot) -> ModelTree:
    """A todo stored with no description at all, as a new row starts out."""

    tree = await create_and_move_to_todo(pilot)
    app = pilot.app
    project = app.project_tree.current_model
    assert isinstance(project, Project)

    made: List[Todo] = []
    await press_writing(pilot, lambda: made.append(project.add_todo()))
    tree.highlight_id(made[0].uuid)
    await pilot.pause()

    assert descriptions(tree) == [""]
    return tree


async def test_e_on_an_empty_description_starts_in_insert():
    async with run_pilot() as pilot:
        tree = await an_empty_todo(pilot)

        await pilot.press("e")
        await pilot.pause()

        engine = field(tree).engine
        assert engine is not None
        assert engine.mode == MODE_INSERT
        assert pilot.app.todooit_mode == "INSERT"

        await commit_line(pilot, "typed")
        assert descriptions(tree) == ["typed"]


async def test_e_on_a_description_starts_in_normal_on_its_last_character():
    async with run_pilot() as pilot:
        tree = await vim_edit(pilot, "hello")

        component = field(tree)
        assert tree.is_editing
        assert component.engine is not None
        assert component.engine.mode == MODE_NORMAL
        assert component.cursor_position == 4
        assert component.selection is None
        assert pilot.app.todooit_mode == "NORMAL"
        assert " NORMAL " in bar_text(pilot.app)


@pytest.mark.parametrize(
    "name, keys, after",
    [
        ("foo bar baz", "=wciwX", "foo X baz"),
        ("one, two", "=dt,", ", two"),
        ("call {it} now", "=di{", "call {} now"),
        ("keep this", "=wD", "keep"),
        ("abc", "x", "ab"),
        ("abc", "rZ", "abZ"),
        ("keep this", "=wCthat", "keep that"),
        ("old name", "ccnew", "new"),
        ("abc", "x=p", "acb"),
        ("abc def", "=2x", "c def"),
        ("a b c d", "=d2w", "c d"),
    ],
)
async def test_motions_and_operators_edit_the_description(name, keys, after):
    async with run_pilot() as pilot:
        tree = await vim_edit(pilot, name)

        await pilot.press(*list(keys))
        await pilot.press("enter")
        await pilot.pause()

        assert not tree.is_editing
        assert descriptions(tree) == [after]


async def test_escape_from_insert_then_from_normal_saves():
    async with run_pilot() as pilot:
        tree = await vim_edit(pilot, "abc")

        await pilot.press("A", "d")
        assert engine(tree).mode == MODE_INSERT

        await pilot.press("escape")
        assert tree.is_editing
        assert engine(tree).mode == MODE_NORMAL
        assert pilot.app.todooit_mode == "NORMAL"

        await pilot.press("escape")
        await pilot.pause()

        assert not tree.is_editing
        assert descriptions(tree) == ["abcd"]


@pytest.mark.parametrize("keys", [["x"], ["A", "!", "escape", "x"]])
async def test_enter_saves_from_normal(keys):
    async with run_pilot() as pilot:
        tree = await vim_edit(pilot, "abc")

        await pilot.press(*keys, "enter")
        await pilot.pause()

        assert not tree.is_editing
        assert descriptions(tree) == ["ab" if keys == ["x"] else "abc"]


async def test_enter_saves_from_insert():
    async with run_pilot() as pilot:
        tree = await vim_edit(pilot, "abc")

        await pilot.press("A", "d", "enter")
        await pilot.pause()

        assert not tree.is_editing
        assert descriptions(tree) == ["abcd"]
        assert pilot.app.todooit_mode == "NORMAL"


async def test_escape_with_an_operator_pending_only_cancels_it():
    async with run_pilot() as pilot:
        tree = await vim_edit(pilot, "abc def")

        await pilot.press("=", "d", "2")
        assert engine(tree).pending == "d2"
        assert " NORMAL d2 " in bar_text(pilot.app)

        await pilot.press("escape")
        await pilot.pause()

        assert tree.is_editing
        assert engine(tree).pending == ""
        assert " NORMAL d2 " not in bar_text(pilot.app)

        # The `w` that would have finished it is only a motion now
        await pilot.press("w", "x", "escape")
        await pilot.pause()

        assert descriptions(tree) == ["abc ef"]


async def test_printable_keys_normal_has_no_use_for_are_swallowed():
    async with run_pilot() as pilot:
        tree = await vim_edit(pilot, "abc")

        # Unbound, or bound to what a description leaves out: yank, visual,
        # search, the note's undo, its flash
        await pilot.press("Q", "y", "v", "?", "u", "s", " ", "tab")
        await pilot.pause()

        assert tree.is_editing
        assert field(tree).value == "abc"
        assert engine(tree).mode == MODE_NORMAL

        await pilot.press("enter")
        assert descriptions(tree) == ["abc"]


async def test_keys_vim_leaves_alone_still_move_the_cursor_in_normal():
    async with run_pilot() as pilot:
        tree = await vim_edit(pilot, "abc")

        await pilot.press("home")
        assert field(tree).cursor_position == 0

        # Never past the last character, as NORMAL stands on one
        await pilot.press("end")
        assert field(tree).cursor_position == 2


async def test_the_panes_keys_never_fire_mid_edit():
    async with run_pilot() as pilot:
        tree = await vim_edit(pilot, "abcdef")

        # `xx` bins a row and `n` adds one, out in the pane
        await pilot.press("=", "x", "x", "n")
        await pilot.pause()

        assert tree.is_editing
        assert len(Todo.all()) == 1

        await pilot.press("escape")
        await pilot.pause()
        assert descriptions(tree) == ["cdef"]


async def test_a_new_empty_row_left_with_escape_escape_is_dropped():
    async with run_pilot() as pilot:
        tree = await an_empty_todo(pilot)

        await pilot.press("e", "escape", "escape")
        await pilot.pause()

        assert not tree.is_editing
        assert Todo.all() == []


async def test_a_row_emptied_in_a_vim_edit_is_dropped_too():
    async with run_pilot() as pilot:
        tree = await vim_edit(pilot, "gone soon")

        await pilot.press("c", "c", "escape", "escape")
        await pilot.pause()

        assert descriptions(tree) == []


@pytest.mark.parametrize("vim", [True, False])
async def test_i_does_nothing_on_a_task(vim):
    async with run_pilot() as pilot:
        tree = await a_todo(pilot, "old")
        pilot.app.api.vim.descriptions = vim

        await pilot.press("i")
        await pilot.pause()

        assert not tree.is_editing
        assert descriptions(tree) == ["old"]


async def test_with_descriptions_switched_off_e_edits_as_i_used_to():
    async with run_pilot() as pilot:
        tree = await a_todo(pilot, "old")
        pilot.app.api.vim.descriptions = False

        # Everything selected, so typing goes over it
        await pilot.press("e")
        assert field(tree).engine is None
        assert field(tree).selection == (0, 3)
        assert pilot.app.todooit_mode == "INSERT"

        await commit_line(pilot, "new")
        assert descriptions(tree) == ["new"]

        # And escape throws the edit away
        await pilot.press("e", "x", "escape")
        await pilot.pause()
        assert descriptions(tree) == ["new"]


async def test_a_delete_in_a_note_pastes_in_a_description():
    async with run_pilot() as pilot:
        await note_holding(pilot, "alpha beta")
        await pilot.press("d", "w")

        # Out of the note, back on its todo
        await pilot.press("escape")
        await pilot.pause()

        tree = pilot.app.api.focused
        await pilot.press("e", "=", "P", "enter")
        await pilot.pause()

        assert descriptions(tree) == ["alpha task with a note"]


async def test_the_panes_u_takes_back_a_whole_vim_edit_at_once():
    async with run_pilot() as pilot:
        tree = await vim_edit(pilot, "abc def")

        await pilot.press("=", "d", "w", "x", "A", "!", "escape", "escape")
        await pilot.pause()
        assert descriptions(tree) == ["ef!"]

        await pilot.press("u")
        await pilot.pause()
        assert descriptions(tree) == ["abc def"]


async def test_a_project_description_takes_the_same_keys():
    async with run_pilot() as pilot:
        await create_and_move_to_todo(pilot)
        tree = pilot.app.project_tree

        await pilot.press("j", "e", "=", "c", "w", "p", "l", "a", "n", "enter")
        await pilot.pause()

        project = tree.current_model
        assert isinstance(project, Project)
        assert project.description == "plan"


async def test_the_bar_says_nav_out_of_an_edit_and_normal_in_one():
    async with run_pilot() as pilot:
        await a_todo(pilot, "abc")
        app = pilot.app
        assert " NAV " in bar_text(app)

        await pilot.press("e")
        await pilot.pause()
        assert " NORMAL " in bar_text(app)
        assert " NAV " not in bar_text(app)

        await pilot.press("i")
        await pilot.pause()
        assert " INSERT " in bar_text(app)

        await pilot.press("escape", "escape")
        await pilot.pause()
        assert " NAV " in bar_text(app)


def cursor_cell(app: Todooit) -> str:
    """The character drawn where the terminal's cursor is, and the one before it."""

    at = app.cursor_position
    line = "".join(segment.text for segment in app.screen._compositor.render_strips()[at.y])
    return line[at.x - 1 : at.x + 1]


async def test_insert_has_the_slim_cursor_between_characters_and_normal_the_block():
    async with run_pilot() as pilot:
        tree = await vim_edit(pilot, "hello world")
        app = pilot.app
        theme = app.api.vars.theme

        # NORMAL: the block on the character, no terminal cursor
        assert not slim_cursor(app).shown
        assert field(tree).editing_cursor_style(theme).bgcolor is not None

        await pilot.press("=", "w", "i")
        await pilot.pause()

        # INSERT: nothing drawn on the character, the terminal's bar before it
        assert slim_cursor(app).shown
        assert field(tree).editing_cursor_style(theme).bgcolor is None
        assert cursor_cell(app) == " w"

        await pilot.press("X")
        await pilot.pause()
        assert cursor_cell(app) == "Xw"

        await pilot.press("escape")
        assert not slim_cursor(app).shown

        await pilot.press("A")
        assert slim_cursor(app).shown

        # Leaving the edit from INSERT puts it away too
        await pilot.press("enter")
        await pilot.pause()
        assert not slim_cursor(app).shown


async def test_the_slim_cursor_is_the_blocks_color():
    async with run_pilot() as pilot:
        tree = await vim_edit(pilot, "abc")
        app = pilot.app
        block = field(tree).editing_cursor_style(app.api.vars.theme).bgcolor

        await pilot.press("i")
        shown = slim_cursor(app)._color
        assert shown is not None and block is not None
        assert block.name == shown.lower()


async def test_a_note_has_the_slim_cursor_in_insert_too():
    async with run_pilot() as pilot:
        screen = await note_holding(pilot, "some text")
        app = pilot.app
        editor = screen.editor

        assert not slim_cursor(app).shown
        assert editor._draw_cursor

        await pilot.press("w", "i")
        await pilot.pause()
        assert slim_cursor(app).shown
        assert not editor._draw_cursor
        assert cursor_cell(app) == " t"

        await pilot.press("escape")
        assert not slim_cursor(app).shown
        assert editor._draw_cursor

        # Closed from INSERT, by whatever way, it's gone with the note
        await pilot.press("i")
        screen.dismiss()
        await pilot.pause()
        assert not slim_cursor(app).shown


def styles_at(tree: ModelTree, theme) -> List[str]:
    """What each character of the field is drawn as: d dimmed, T a target, . plain."""

    text = field(tree).render_editing(theme)
    marks = []

    for at in range(len(field(tree).value)):
        style = Style.combine(
            [Style()]
            + [
                span.style
                for span in text.spans
                if span.start <= at < span.end and isinstance(span.style, Style)
            ]
        )
        if style.bgcolor == target_style(theme).bgcolor:
            marks.append("T")
        elif style.color == backdrop_style(theme).color:
            marks.append("d")
        else:
            marks.append(".")

    return marks


async def test_f_dims_what_it_looks_across_and_lights_up_its_targets():
    async with run_pilot() as pilot:
        tree = await vim_edit(pilot, "a,b,c")
        theme = pilot.app.api.vars.theme

        await pilot.press("=", "f")
        assert "".join(styles_at(tree, theme)) == ".dddd"

        await pilot.press(",")
        assert field(tree).cursor_position == 1
        assert "".join(styles_at(tree, theme)[2:]) == "dTd"

        # Escape puts the targets out, and only the next one saves
        await pilot.press("escape")
        await pilot.pause()
        assert tree.is_editing
        assert "".join(styles_at(tree, theme)) == "....."

        await pilot.press("escape")
        await pilot.pause()
        assert not tree.is_editing


async def test_capital_f_dims_what_is_behind_instead():
    async with run_pilot() as pilot:
        tree = await vim_edit(pilot, "a,b,c")
        theme = pilot.app.api.vars.theme

        await pilot.press("F")
        assert "".join(styles_at(tree, theme)) == "dddd."


async def test_a_new_task_starts_in_insert_and_escape_goes_on_to_normal():
    async with run_pilot() as pilot:
        tree = await create_and_move_to_todo(pilot)

        await pilot.press("n")
        await pilot.pause()
        assert engine(tree).mode == MODE_INSERT
        assert slim_cursor(pilot.app).shown

        await pilot.press(*list("asd"), "escape")
        await pilot.pause()

        # Still there, being edited, in NORMAL on its last character
        assert tree.is_editing
        assert engine(tree).mode == MODE_NORMAL
        assert field(tree).cursor_position == 2
        assert len(Todo.all()) == 1

        await pilot.press("x", "escape")
        await pilot.pause()
        assert descriptions(tree) == ["as"]


async def test_a_new_step_starts_in_insert_too():
    async with run_pilot() as pilot:
        await a_todo(pilot, "task")

        await pilot.press("N", *list("step"), "escape", "escape")
        await pilot.pause()

        assert sorted(t.description for t in Todo.all()) == ["step", "task"]


async def test_with_descriptions_switched_off_escape_still_drops_a_new_task():
    async with run_pilot() as pilot:
        tree = await create_and_move_to_todo(pilot)
        pilot.app.api.vim.descriptions = False

        await pilot.press("n", *list("never kept"), "escape")
        await pilot.pause()

        assert not tree.is_editing
        assert Todo.all() == []
