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
from todooit.ui.screens.note.markdown import (
    PASTE_INLINE,
    PASTE_STRIP,
    from_markdown,
    to_markdown,
)
from todooit.ui.screens.note.markup import EMPH_MARK, QUOTE_GLYPH

RULE = "─" * 10
M = EMPH_MARK


@pytest.mark.parametrize(
    "markdown, stored",
    [
        # Every heading depth is the note's one header
        ("# Title", "Title\n" + RULE),
        ("### Title ###", "Title\n" + RULE),
        ("Title\n===", "Title\n" + RULE),
        ("Title\n---", "Title\n" + RULE),
        ("#hashtag", "#hashtag"),
        # Every emphasis is the note's one emphasis
        ("**bold** and *it*", f"{M}bold{M} and {M}it{M}"),
        ("***both*** __u__ _x_", f"{M}both{M} {M}u{M} {M}x{M}"),
        ("snake_case_name", "snake_case_name"),
        ("a * b * c", "a * b * c"),
        (r"\*not\* emphasis", "*not* emphasis"),
        # Every bullet is a glyph, nested by however the file indents
        ("- a\n* b\n+ c", "• a\n• b\n• c"),
        ("- a\n    - b\n        - c", "• a\n  ◦ b\n    ▪ c"),
        ("- a\n\t- b", "• a\n  ◦ b"),
        ("  - a\n    - b", "• a\n  ◦ b"),
        # Enumerations keep their numbers (the editor recounts them)
        ("1. a\n2) b\n   - c", "1. a\n2. b\n  ◦ c"),
        # Quotes, nested or not, are the one quote bar
        ("> a\n> > b\n>c", f"{QUOTE_GLYPH}a\n{QUOTE_GLYPH}b\n{QUOTE_GLYPH}c"),
        ("> - a", f"{QUOTE_GLYPH}• a"),
        # A thematic break is a rule, kept off the text above it
        ("***", RULE),
        ("text\n\n* * *", "text\n\n" + RULE),
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
    assert from_markdown(markdown, RULE) == stored


def test_a_rule_pasted_under_text_keeps_off_it():
    """Straight under a line of words, a rule would be that line's header"""

    assert from_markdown("---", RULE, above="words") == "\n" + RULE
    assert from_markdown("---", RULE, above="") == RULE


def test_the_first_line_mid_line_takes_only_emphasis():
    assert from_markdown("# not *here*\n- but here", RULE, PASTE_INLINE) == (
        f"# not {M}here{M}\n• but here"
    )


def test_the_first_line_after_a_marker_drops_its_own():
    assert from_markdown("- item", RULE, PASTE_STRIP) == "item"
    assert from_markdown("## title", RULE, PASTE_STRIP) == "title"


@pytest.mark.parametrize(
    "stored, markdown",
    [
        ("Title\n" + RULE + "\nbody", "# Title\nbody"),
        ("above\n\n" + RULE, "above\n\n---"),
        ("• a\n  ◦ b\n    ▪ c", "- a\n  - b\n    - c"),
        # Markdown nests under a number at its words, three columns in
        ("1. a\n  • b", "1. a\n   - b"),
        (f"{QUOTE_GLYPH}quoted\nafter", "> quoted\n\nafter"),
        (f"{QUOTE_GLYPH}• item", "> - item"),
        (f"{M}bold{M} words", "**bold** words"),
        (f"{M} spaced {M}", " **spaced** "),
        (f"orphan{M} mark", "orphan mark"),
        ("[docs](https://example.com)", "[docs](https://example.com)"),
    ],
)
def test_to_markdown(stored, markdown):
    assert to_markdown(stored) == markdown


def test_a_note_survives_the_round_trip():
    stored = (
        "Plan\n" + RULE + "\n"
        f"some {M}bold{M} words\n"
        "• one\n  ◦ two\n"
        "1. first\n2. second\n\n"
        f"{QUOTE_GLYPH}said\n\n" + RULE
    )

    assert from_markdown(to_markdown(stored), RULE) == stored


async def test_copying_the_note_writes_markdown():
    async with run_pilot() as pilot:
        screen = await open_note(pilot)
        editor = screen.editor

        editor.load_text("Plan\n" + editor.rule + f"\n• one\n{QUOTE_GLYPH}{M}said{M}")
        await pilot.pause()

        await pilot.press("ctrl+c")
        await pilot.pause()

        assert pilot.app.clipboard == "# Plan\n- one\n> **said**"

        await pilot.press("escape", "escape")
        await pilot.pause()


async def test_pasting_markdown_writes_the_markup_it_types_as():
    async with run_pilot() as pilot:
        screen = await open_note(pilot)
        editor = screen.editor

        set_clipboard("## Plan\n* **one**\n1. a\n1. b")
        await pilot.press("ctrl+v")
        await pilot.pause()

        # The pasted list is numbered as a list typed in would be
        assert editor.text == f"Plan\n{editor.rule}\n• {M}one{M}\n1. a\n2. b"
        assert editor.cursor_location == (4, len("2. b"))

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
        editor.post_message(events.Paste("\n> **quoted**"))
        await pilot.pause()

        assert editor.text == f"written\n{QUOTE_GLYPH}{M}quoted{M}"
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

        assert editor.text == f"count: # 1 {M}more{M}"

        await pilot.press("escape", "escape")
        await pilot.pause()


async def test_pasting_a_bullet_onto_a_bullet_makes_one():
    async with run_pilot() as pilot:
        screen = await open_note(pilot)
        editor = screen.editor

        editor.load_text("• ")
        await pilot.pause()

        editor.move_cursor((0, 2))
        set_clipboard("- item\n- next")
        await pilot.press("ctrl+v")
        await pilot.pause()

        assert editor.text == "• item\n• next"

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
