"""
Notes and markdown: copies are written as markdown, pastes read as it
"""

import pytest
from textual import events

from tests.test_ui.test_note_ui import open_note
from tests.test_ui.ui_base import (
    commit_line,
    create_and_move_to_todo,
    run_pilot,
    set_clipboard,
)
from todooit.ui.screens.note.disp.markdown import (
    EMPH_MARK,
    OLD_QUOTE_GLYPH,
    PASTE_INLINE,
    PASTE_STRIP,
    from_markdown,
    to_markdown,
)

RULE = "─" * 10
M = EMPH_MARK


@pytest.mark.parametrize(
    "markdown, stored",
    [
        # Every heading depth is the note's one header
        ("# Title", "# Title"),
        ("### Title ###", "# Title"),
        ("Title\n===", "# Title"),
        ("Title\n---", "# Title"),
        ("#hashtag", "#hashtag"),
        # Stars are read as they are, underscores become stars
        ("**bold** and *it*", "**bold** and *it*"),
        ("***both*** __u__ _x_", "***both*** **u** **x**"),
        ("snake_case_name", "snake_case_name"),
        ("a * b * c", "a * b * c"),
        (r"\*not\* emphasis", "*not* emphasis"),
        # Every bullet is a dash, nested by however the file indents
        ("- a\n* b\n+ c", "- a\n- b\n- c"),
        ("- a\n    - b\n        - c", "- a\n  - b\n    - c"),
        ("- a\n\t- b", "- a\n  - b"),
        ("  - a\n    - b", "- a\n  - b"),
        # Enumerations keep their numbers (the editor recounts them)
        ("1. a\n2) b\n   - c", "1. a\n2. b\n  - c"),
        # Quotes, nested or not, are the one quote
        ("> a\n> > b\n>c", "> a\n> b\n> c"),
        ("> - a", "> - a"),
        # A thematic break is a rule, kept off the text above it
        ("***", "---"),
        ("text\n\n* * *", "text\n\n---"),
        # Links, code and code blocks pass through as written
        ("[docs](https://example.com/a_b_c_)", "[docs](https://example.com/a_b_c_)"),
        ("`*ptr*`", "`*ptr*`"),
        ("```\n# comment\n- x\n```", "```\n# comment\n- x\n```"),
        # Hard breaks go; the last line runs on into the note, so it keeps its space
        ("a  \nb ", "a\nb "),
        ("a\r\nb", "a\nb"),
    ],
)
def test_from_markdown(markdown, stored):
    assert from_markdown(markdown) == stored


def test_a_rule_pasted_under_text_keeps_off_it():
    """Straight under a line of words, a rule would be that line's underline elsewhere"""

    assert from_markdown("---", above="words") == "\n---"
    assert from_markdown("---", above="") == "---"


def test_the_first_line_mid_line_is_left_as_words():
    assert from_markdown("# not _here_\n- but here", PASTE_INLINE) == (
        "# not **here**\n- but here"
    )


def test_the_first_line_after_a_marker_drops_its_own():
    assert from_markdown("- item", PASTE_STRIP) == "item"
    assert from_markdown("## title", PASTE_STRIP) == "title"


@pytest.mark.parametrize(
    "stored, markdown",
    [
        ("Title\n" + RULE + "\nbody", "# Title\nbody"),
        ("above\n\n" + RULE, "above\n\n---"),
        ("• a\n  ◦ b\n    ▪ c", "- a\n  - b\n    - c"),
        # Markdown nests under a number at its words, three columns in
        ("1. a\n  • b", "1. a\n   - b"),
        (f"{OLD_QUOTE_GLYPH}quoted\nafter", "> quoted\n\nafter"),
        (f"{OLD_QUOTE_GLYPH}• item", "> - item"),
        (f"{M}bold{M} words", "**bold** words"),
        (f"{M} spaced {M}", " **spaced** "),
        (f"orphan{M} mark", "orphan mark"),
        ("[docs](https://example.com)", "[docs](https://example.com)"),
    ],
)
def test_to_markdown(stored, markdown):
    assert to_markdown(stored) == markdown


async def test_pasting_markdown_stores_it_and_numbers_the_list():
    async with run_pilot() as pilot:
        screen = await open_note(pilot)
        editor = screen.editor

        set_clipboard("## Plan\n* **one**\n1. a\n1. b")
        await pilot.press("ctrl+v")
        await pilot.pause()

        # The pasted list is numbered as a list typed in would be
        assert editor.text == "# Plan\n- **one**\n1. a\n2. b"
        assert editor.cursor_location == (3, len("2. b"))

        await pilot.press("escape", "escape")
        await pilot.pause()


async def test_the_terminals_own_paste_reads_markdown_too():
    """
    Windows Terminal hands ctrl+v and right-click to the app as a paste of its
    own, which used to land verbatim, and not at all in NORMAL
    """

    async with run_pilot() as pilot:
        screen = await open_note(pilot)
        editor = screen.editor

        editor.load_text("written")
        await pilot.press("escape")
        await pilot.pause()

        editor.move_cursor((0, len("written")))
        editor.post_message(events.Paste("\n> > **quoted**"))
        await pilot.pause()

        assert editor.text == "written\n> **quoted**"
        assert screen.editor.mode == "INSERT"

        await pilot.press("escape", "escape")
        await pilot.pause()


async def test_pasting_mid_line_leaves_line_markup_as_words():
    async with run_pilot() as pilot:
        screen = await open_note(pilot)
        editor = screen.editor

        editor.load_text("count: ")
        await pilot.pause()

        editor.move_cursor((0, len("count: ")))
        set_clipboard("# 1 *more*")
        await pilot.press("ctrl+v")
        await pilot.pause()

        assert editor.text == "count: # 1 *more*"

        await pilot.press("escape", "escape")
        await pilot.pause()


async def test_pasting_a_bullet_onto_a_bullet_makes_one():
    async with run_pilot() as pilot:
        screen = await open_note(pilot)
        editor = screen.editor

        editor.load_text("- ")
        await pilot.pause()

        editor.move_cursor((0, 2))
        set_clipboard("- item\n- next")
        await pilot.press("ctrl+v")
        await pilot.pause()

        assert editor.text == "- item\n- next"

        await pilot.press("escape", "escape")
        await pilot.pause()


async def test_copying_a_note_from_the_list_writes_markdown():
    async with run_pilot() as pilot:
        tree = await create_and_move_to_todo(pilot)

        await pilot.press("n")
        await commit_line(pilot, "task with a note")

        todo = tree.current_model
        todo.note = f"• {M}one{M}\n  ◦ two"
        todo.save()

        await pilot.press("ctrl+n")
        await pilot.pause()

        assert pilot.app.clipboard == "- **one**\n  - two"
