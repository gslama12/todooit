"""
The vim engine on its own: keys go in, text, cursor and mode come out

Nothing here knows about Textual. The engine drives a buffer held in memory, as
any host would drive it.
"""

import ast
from pathlib import Path
from typing import List, Set, Tuple

import pytest

import todooit.vim_engine
from todooit.vim_engine import (
    MODE_INSERT,
    MODE_NORMAL,
    FindView,
    Register,
    VimCommand,
    VimEngine,
    VimKeymap,
    VimMotion,
    VimOperator,
)


class MemoryBuffer:
    """The smallest host there is: lines of text and a cursor."""

    def __init__(self, text: str, cursor: Tuple[int, int] = (0, 0)) -> None:
        self.lines: List[str] = text.split("\n")
        self.cursor = cursor
        self.modes: List[str] = []
        self.visible_rows = range(len(self.lines))
        self.half_page = 5
        self.vertical: List[Tuple[str, int]] = []
        self.centred = 0
        self.links_opened = 0
        self.files_picked = 0

    @property
    def line_count(self) -> int:
        return len(self.lines)

    def line(self, row: int) -> str:
        return self.lines[row]

    def move_cursor(self, row: int, column: int) -> None:
        self.cursor = (row, column)

    def replace(
        self, start: Tuple[int, int], end: Tuple[int, int], text: str
    ) -> None:
        head = self.lines[start[0]][: start[1]]
        tail = self.lines[end[0]][end[1] :]
        self.lines[start[0] : end[0] + 1] = (head + text + tail).split("\n")

    def _go_down(self, delta: int) -> None:
        row = max(0, min(self.cursor[0] + delta, self.line_count - 1))
        self.cursor = (row, min(self.cursor[1], len(self.lines[row])))

    def move_rows(self, delta: int) -> None:
        self.vertical.append(("rows", delta))
        self._go_down(delta)

    def move_lines(self, delta: int) -> None:
        self.vertical.append(("lines", delta))
        self._go_down(delta)

    def scroll_rows(self, delta: int) -> None:
        self.vertical.append(("page", delta))
        self._go_down(delta)

    def center_view(self) -> None:
        self.centred += 1

    def open_link(self) -> None:
        self.links_opened += 1

    def pick_files(self) -> None:
        self.files_picked += 1

    def mode_changed(self, mode: str) -> None:
        self.modes.append(mode)

    @property
    def text(self) -> str:
        return "\n".join(self.lines)


def default_keys() -> VimKeymap:
    keys = VimKeymap()
    keys.set("j", VimMotion.LEFT)
    keys.set("ö", VimMotion.RIGHT)
    keys.set("k", VimMotion.UP)
    keys.set("l", VimMotion.DOWN)
    keys.set("i", VimCommand.INSERT)
    keys.set("<ctrl+u>", VimMotion.HALF_PAGE_UP)
    keys.set("<ctrl+d>", VimMotion.HALF_PAGE_DOWN)
    keys.set("gg", VimMotion.TOP)
    keys.set("G", VimMotion.BOTTOM)
    keys.set("{", VimMotion.PARAGRAPH_UP)
    keys.set("}", VimMotion.PARAGRAPH_DOWN)
    keys.set("zz", VimCommand.CENTER_VIEW)
    keys.set("gx", VimCommand.OPEN_LINK)
    keys.set("gf", VimCommand.PICK_FILES)
    return keys


def engine_on(text: str, cursor: Tuple[int, int] = (0, 0), **options) -> VimEngine:
    return VimEngine(MemoryBuffer(text, cursor), default_keys(), **options)


def buffer_of(engine: VimEngine) -> MemoryBuffer:
    assert isinstance(engine.buffer, MemoryBuffer)
    return engine.buffer


def feed(engine: VimEngine, keys: str) -> None:
    for key in keys:
        engine.feed(key)


@pytest.mark.parametrize(
    "start, keys, end",
    [
        ((0, 1), "j", (0, 0)),
        ((0, 1), "ö", (0, 2)),
        ((1, 1), "k", (0, 1)),
        ((0, 1), "l", (1, 1)),
    ],
)
def test_the_four_motions_move_the_cursor(start, keys, end):
    engine = engine_on("abc\ndef", start)

    feed(engine, keys)

    assert buffer_of(engine).cursor == end
    assert buffer_of(engine).text == "abc\ndef"
    assert engine.mode == MODE_NORMAL


def test_left_stops_at_the_start_of_the_line():
    engine = engine_on("abc\ndef", (1, 0))

    feed(engine, "j")

    assert buffer_of(engine).cursor == (1, 0)


def test_right_stops_on_the_last_character():
    engine = engine_on("abc\ndef", (0, 2))

    feed(engine, "ö")

    assert buffer_of(engine).cursor == (0, 2)


def test_up_and_down_stop_at_the_ends_of_the_text():
    engine = engine_on("abc\ndef", (0, 0))

    feed(engine, "k")
    assert buffer_of(engine).cursor == (0, 0)

    feed(engine, "ll")
    assert buffer_of(engine).cursor == (1, 0)


def test_moving_onto_a_shorter_line_lands_on_its_last_character():
    engine = engine_on("abcdef\nxy", (0, 5))

    feed(engine, "l")

    assert buffer_of(engine).cursor == (1, 1)


def test_an_empty_line_holds_the_cursor_at_its_start():
    engine = engine_on("abc\n\ndef", (0, 2))

    feed(engine, "l")
    assert buffer_of(engine).cursor == (1, 0)

    feed(engine, "ö")
    assert buffer_of(engine).cursor == (1, 0)


def test_motions_work_on_an_empty_text():
    engine = engine_on("")

    feed(engine, "jökl")

    assert buffer_of(engine).cursor == (0, 0)


def test_the_insert_command_enters_insert_and_tells_the_host():
    engine = engine_on("abc")

    feed(engine, "i")

    assert engine.mode == MODE_INSERT
    assert buffer_of(engine).modes == [MODE_INSERT]


def test_keys_are_left_to_the_host_in_insert():
    engine = engine_on("abc", (0, 1))
    feed(engine, "i")

    assert engine.feed("j") is False
    assert buffer_of(engine).cursor == (0, 1)


def test_escape_leaves_insert_and_clamps_the_cursor():
    # Past the last character is where a cursor sits after typing at a line's end
    engine = engine_on("abc", (0, 3))
    feed(engine, "i")

    assert engine.feed("escape") is True

    assert engine.mode == MODE_NORMAL
    assert buffer_of(engine).cursor == (0, 2)
    assert buffer_of(engine).modes == [MODE_INSERT, MODE_NORMAL]


def test_escape_is_left_to_the_host_in_plain_normal():
    # Nothing left to leave, so the host decides: the note window closes on it
    assert engine_on("abc").feed("escape") is False


def test_a_key_with_no_binding_is_left_to_the_host():
    engine = engine_on("abc", (0, 1))

    assert engine.feed("Q") is False
    assert buffer_of(engine).cursor == (0, 1)


def test_a_bound_key_is_reported_as_handled():
    assert engine_on("abc").feed("ö") is True


def test_a_host_can_switch_off_what_needs_several_lines():
    engine = engine_on("abc\ndef", (0, 1), multiline=False)

    assert engine.feed("l") is False
    assert buffer_of(engine).cursor == (0, 1)

    # Moving along the line has nothing to do with that
    assert engine.feed("ö") is True
    assert buffer_of(engine).cursor == (0, 2)


def test_the_keymap_decides_what_a_key_does():
    keys = default_keys()
    keys.remap({"j": "h", "ö": "j"})
    engine = VimEngine(MemoryBuffer("abc", (0, 1)), keys)

    feed(engine, "h")
    assert buffer_of(engine).cursor == (0, 0)

    feed(engine, "j")
    assert buffer_of(engine).cursor == (0, 1)


def test_a_changed_keymap_applies_to_a_running_engine():
    keys = default_keys()
    engine = VimEngine(MemoryBuffer("abc", (0, 1)), keys)

    keys.set("x", VimMotion.RIGHT)
    feed(engine, "x")

    assert buffer_of(engine).cursor == (0, 2)


def test_set_takes_several_keys_for_one_command():
    keys = VimKeymap()
    keys.set(["x", "y"], VimMotion.RIGHT)
    engine = VimEngine(MemoryBuffer("abcd"), keys)

    feed(engine, "xy")

    assert buffer_of(engine).cursor == (0, 2)


def test_a_binding_can_take_several_keys_in_a_row():
    keys = default_keys()
    keys.set("gj", VimMotion.RIGHT)
    engine = VimEngine(MemoryBuffer("abc"), keys)

    assert engine.feed("g") is True
    assert engine.pending == "g"
    assert buffer_of(engine).cursor == (0, 0)

    assert engine.feed("j") is True
    assert engine.pending == ""
    assert buffer_of(engine).cursor == (0, 1)


def test_a_key_that_fits_no_binding_cancels_the_pending_ones_silently():
    keys = default_keys()
    keys.set("gj", VimMotion.RIGHT)
    engine = VimEngine(MemoryBuffer("abc", (0, 1)), keys)

    feed(engine, "gz")

    assert engine.pending == ""
    assert buffer_of(engine).cursor == (0, 1)


def test_escape_cancels_pending_keys_before_anything_else():
    keys = default_keys()
    keys.set("gj", VimMotion.RIGHT)
    engine = VimEngine(MemoryBuffer("abc"), keys)
    feed(engine, "g")

    # Handled, so the host doesn't also close the note
    assert engine.feed("escape") is True
    assert engine.pending == ""
    assert engine.feed("escape") is False


def test_a_named_key_can_be_bound_in_angle_brackets():
    keys = VimKeymap()
    keys.set("<ctrl+f>", VimMotion.RIGHT)
    engine = VimEngine(MemoryBuffer("abc"), keys)

    assert engine.feed("ctrl+f") is True
    assert buffer_of(engine).cursor == (0, 1)


def test_remap_can_swap_keys():
    keys = default_keys()
    keys.remap({"j": "ö", "ö": "j"})
    engine = VimEngine(MemoryBuffer("abc", (0, 1)), keys)

    feed(engine, "ö")

    assert buffer_of(engine).cursor == (0, 0)


def test_remap_refuses_a_key_with_nothing_on_it():
    with pytest.raises(KeyError, match="z"):
        default_keys().remap({"z": "x"})


def test_remap_refuses_to_overwrite_a_binding_that_stays():
    with pytest.raises(ValueError, match="k"):
        default_keys().remap({"j": "k"})


def test_the_keymap_says_which_key_a_command_is_on():
    keys = default_keys()

    assert keys.key_for(VimMotion.UP) == "k"

    keys.remap({"k": "w"})

    assert keys.key_for(VimMotion.UP) == "w"
    assert VimKeymap().key_for(VimMotion.UP) is None


def test_the_engine_package_imports_nothing_from_the_ui():
    package = Path(todooit.vim_engine.__file__).parent

    imported: Set[str] = set()
    for path in package.glob("*.py"):
        for node in ast.walk(ast.parse(path.read_text(encoding="utf-8"))):
            if isinstance(node, ast.Import):
                imported.update(alias.name for alias in node.names)
            elif isinstance(node, ast.ImportFrom) and node.level == 0:
                imported.add(node.module or "")

    assert imported, "the scan found no imports at all, so it isn't reading the package"
    assert not {
        name
        for name in imported
        if name.split(".")[0] in ("textual", "rich") or name.startswith("todooit.ui")
    }


# ---------------------------------------------------------------------------
# Word, line and character motions, and counts
# ---------------------------------------------------------------------------


def motion_keys() -> VimKeymap:
    keys = default_keys()
    keys.set("w", VimMotion.WORD_FORWARD)
    keys.set("b", VimMotion.WORD_BACKWARD)
    keys.set("e", VimMotion.WORD_END)
    keys.set("=", VimMotion.FIRST_NON_BLANK)
    keys.set("_", VimMotion.LAST_CHARACTER)
    keys.set("ü", VimMotion.LINE_ABOVE)
    keys.set("ä", VimMotion.LINE_BELOW)
    keys.set("f", VimMotion.FIND_FORWARD)
    keys.set("F", VimMotion.FIND_BACKWARD)
    keys.set("t", VimMotion.TILL_FORWARD)
    keys.set("T", VimMotion.TILL_BACKWARD)
    keys.set("h", VimMotion.REPEAT_FIND)
    keys.set("H", VimMotion.REVERSE_FIND)
    return keys


def run_keys(text: str, start: Tuple[int, int], keys: str) -> Tuple[int, int]:
    """Where the cursor ends up, having checked that moving wrote nothing."""

    engine = VimEngine(MemoryBuffer(text, start), motion_keys())
    feed(engine, keys)

    assert buffer_of(engine).text == text
    assert engine.mode == MODE_NORMAL
    assert engine.pending == ""
    return buffer_of(engine).cursor


@pytest.mark.parametrize(
    "text, start, keys, end",
    [
        # w: the start of the next word
        ("foo bar", (0, 0), "w", (0, 4)),
        ("foo   bar", (0, 1), "w", (0, 6)),
        # Punctuation is a word of its own, as in vim
        ("foo.bar", (0, 0), "w", (0, 3)),
        ("foo.bar", (0, 3), "w", (0, 4)),
        ("foo...bar", (0, 3), "w", (0, 6)),
        # Letters, digits, `_` and umlauts are all one word
        ("a_1b c", (0, 0), "w", (0, 5)),
        ("über größe", (0, 0), "w", (0, 5)),
        ("größe.x", (0, 0), "w", (0, 5)),
        # An umlaut stored as a letter and a combining mark, as macOS may paste it
        ("gru\u0308n x", (0, 0), "w", (0, 6)),
        # On to the next line, where an empty line counts as a word
        ("foo\nbar", (0, 0), "w", (1, 0)),
        ("foo\n  bar", (0, 0), "w", (1, 2)),
        ("foo\n\nbar", (0, 0), "w", (1, 0)),
        ("foo\n\nbar", (1, 0), "w", (2, 0)),
        ("foo\n   \nbar", (0, 0), "w", (2, 0)),
        # Nowhere left to go: the last character
        ("foo bar", (0, 5), "w", (0, 6)),
        ("foo bar  ", (0, 5), "w", (0, 8)),
        ("", (0, 0), "w", (0, 0)),
        # b: the start of this word, or else of the one before
        ("foo bar", (0, 6), "b", (0, 4)),
        ("foo bar", (0, 4), "b", (0, 0)),
        ("foo   bar", (0, 5), "b", (0, 0)),
        ("foo.bar", (0, 4), "b", (0, 3)),
        ("foo.bar", (0, 3), "b", (0, 0)),
        ("größe x", (0, 6), "b", (0, 0)),
        ("foo\nbar", (1, 0), "b", (0, 0)),
        ("foo\n\nbar", (2, 0), "b", (1, 0)),
        ("foo\n\nbar", (1, 0), "b", (0, 0)),
        ("foo\n   \nbar", (2, 0), "b", (0, 0)),
        ("  foo", (0, 2), "b", (0, 0)),
        ("foo", (0, 0), "b", (0, 0)),
        # e: the end of this word, or else of the next
        ("foo bar", (0, 0), "e", (0, 2)),
        ("foo bar", (0, 2), "e", (0, 6)),
        ("foo.bar", (0, 0), "e", (0, 2)),
        ("foo.bar", (0, 2), "e", (0, 3)),
        ("größe x", (0, 0), "e", (0, 4)),
        # Unlike w, an empty line isn't an end to stop on
        ("foo\n\nbar", (0, 2), "e", (2, 2)),
        ("foo bar  ", (0, 6), "e", (0, 8)),
    ],
)
def test_word_motions(text, start, keys, end):
    assert run_keys(text, start, keys) == end


@pytest.mark.parametrize(
    "text, start, keys, end",
    [
        ("   foo bar", (0, 8), "=", (0, 3)),
        ("foo", (0, 2), "=", (0, 0)),
        # Nothing but blanks: as far along as a cursor can stand
        ("    ", (0, 0), "=", (0, 3)),
        ("", (0, 0), "=", (0, 0)),
        ("foo bar", (0, 1), "_", (0, 6)),
        ("foo bar  ", (0, 1), "_", (0, 8)),
        ("", (0, 0), "_", (0, 0)),
        ("  a\n    b", (1, 6), "ü", (0, 2)),
        ("  a\n    b", (0, 0), "ä", (1, 4)),
        ("a\n\nb", (2, 0), "ü", (1, 0)),
        # Nothing above or below: stays exactly where it was
        ("  a\nb", (0, 0), "ü", (0, 0)),
        ("a\n  bcd", (1, 3), "ä", (1, 3)),
    ],
)
def test_line_motions(text, start, keys, end):
    assert run_keys(text, start, keys) == end


@pytest.mark.parametrize(
    "start, keys, end",
    [
        ((0, 0), "fb", (0, 2)),
        ((0, 2), "fb", (0, 6)),
        ((0, 6), "Fb", (0, 2)),
        ((0, 0), "tb", (0, 1)),
        ((0, 6), "Tb", (0, 3)),
        # The character isn't there: stays put
        ((0, 0), "fz", (0, 0)),
        ((0, 6), "Fz", (0, 6)),
        ((0, 0), "tz", (0, 0)),
        ((0, 0), "Tb", (0, 0)),
        # On through the lines after this one
        ((0, 8), "fq", (1, 0)),
    ],
)
def test_character_jumps(start, keys, end):
    assert run_keys("a b c b d\nq", start, keys) == end


def test_a_character_jump_can_land_on_a_space_or_an_umlaut():
    assert run_keys("ab cö", (0, 0), "f ") == (0, 2)
    assert run_keys("ab cö", (0, 0), "fö") == (0, 4)


def test_a_key_that_is_bound_still_names_a_character_after_f():
    # `j` means left, but right after an f it is only a letter to look for
    assert run_keys("a j", (0, 0), "fj") == (0, 2)
    # A digit too, which would otherwise start a count
    assert run_keys("a 2", (0, 0), "f2") == (0, 2)


@pytest.mark.parametrize(
    "start, keys, end",
    [
        ((0, 0), "fbh", (0, 6)),
        ((0, 8), "Fbh", (0, 2)),
        # h after t gets past the character it's standing next to, as in vim
        ((0, 0), "tbh", (0, 5)),
        ((0, 8), "Tbh", (0, 3)),
        # H goes the other way
        ((0, 0), "fbhH", (0, 2)),
        ((0, 8), "FbH", (0, 6)),
        ((0, 6), "FbH", (0, 6)),
        # H goes back to a place already marked, so after t it's still before
        ((0, 0), "tbhH", (0, 1)),
        # H doesn't turn the jump around for good: h is still forward after it
        ((0, 0), "fbhHh", (0, 6)),
        # A jump that found nothing is still the last jump
        ((0, 0), "fzh", (0, 0)),
    ],
)
def test_repeating_a_character_jump(start, keys, end):
    assert run_keys("a b c b d\nq", start, keys) == end


def test_repeating_with_no_jump_yet_does_nothing():
    assert run_keys("a b", (0, 1), "h") == (0, 1)
    assert run_keys("a b", (0, 1), "H") == (0, 1)


@pytest.mark.parametrize(
    "text, start, keys, end",
    [
        ("one two three four", (0, 0), "3w", (0, 14)),
        ("one two\nthree four", (0, 0), "2w", (1, 0)),
        ("one two three four", (0, 16), "3b", (0, 4)),
        ("one two three four", (0, 0), "2e", (0, 6)),
        # More than there is: as far as it goes
        ("one two", (0, 0), "99w", (0, 6)),
        ("one two", (0, 6), "99b", (0, 0)),
        ("one two", (0, 0), "99e", (0, 6)),
        # Several digits, including a zero after the first
        ("abcdefghijklmn", (0, 0), "10ö", (0, 10)),
        ("abcdefghijklmn", (0, 12), "10j", (0, 2)),
        ("abc", (0, 0), "9ö", (0, 2)),
        ("abc", (0, 2), "9j", (0, 0)),
        ("a\nb\nc\nd", (0, 0), "2l", (2, 0)),
        ("a\nb\nc\nd", (3, 0), "2k", (1, 0)),
        # = and _ count lines, this one being the first
        ("a\n  b\n  cd", (0, 0), "2=", (1, 2)),
        ("a\nbcd\nef", (0, 0), "2_", (1, 2)),
        ("a\nbcd", (0, 0), "9_", (1, 2)),
        ("a\n  b\nc\n  d", (0, 0), "3ä", (3, 2)),
        ("  a\nb\nc\nd", (3, 0), "3ü", (0, 2)),
        # More lines than there are: as far as they go
        ("a\n  b", (0, 0), "9ä", (1, 2)),
        ("  a\nb", (1, 0), "9ü", (0, 2)),
        # The nth one along, or no move at all
        ("a b c b d", (0, 0), "2fb", (0, 6)),
        ("a b c b d", (0, 8), "2Fb", (0, 2)),
        ("a b c b d", (0, 0), "2tb", (0, 5)),
        ("a b c b d", (0, 8), "2Tb", (0, 3)),
        ("a b c b d", (0, 0), "3fb", (0, 0)),
        # h and H take one, and the count of the jump isn't remembered
        ("b b b b b", (0, 0), "2fb", (0, 4)),
        ("b b b b b", (0, 0), "fb2h", (0, 6)),
        ("b b b b b", (0, 0), "2fbh", (0, 6)),
        ("b b b b b", (0, 8), "Fb2H", (0, 6)),
        ("a b b b", (0, 0), "tb2h", (0, 5)),
    ],
)
def test_counts(text, start, keys, end):
    assert run_keys(text, start, keys) == end


def test_a_count_is_used_up_by_the_motion_it_came_with():
    assert run_keys("a b c d e", (0, 0), "2ww") == (0, 6)


def test_a_zero_alone_is_not_a_count():
    engine = VimEngine(MemoryBuffer("abc", (0, 1)), motion_keys())

    # Left to the host, which may have a use for it
    assert engine.feed("0") is False
    assert engine.pending == ""


def test_a_key_bound_to_zero_still_works():
    keys = motion_keys()
    keys.set("0", VimMotion.FIRST_NON_BLANK)
    engine = VimEngine(MemoryBuffer("  abc", (0, 4)), keys)

    feed(engine, "0")
    assert buffer_of(engine).cursor == (0, 2)
    assert engine.pending == ""


def test_a_zero_after_a_count_is_part_of_it_even_when_bound():
    keys = motion_keys()
    keys.set("0", VimMotion.FIRST_NON_BLANK)
    engine = VimEngine(MemoryBuffer("a" * 15), keys)

    feed(engine, "10")
    assert engine.pending == "10"

    feed(engine, "ö")
    assert buffer_of(engine).cursor == (0, 10)


def test_a_digit_bound_to_a_command_is_that_command():
    keys = motion_keys()
    keys.set("5", VimMotion.RIGHT)
    engine = VimEngine(MemoryBuffer("abc"), keys)

    feed(engine, "5")

    assert buffer_of(engine).cursor == (0, 1)
    assert engine.pending == ""


@pytest.mark.parametrize(
    "keys, pending",
    [
        ("2", "2"),
        ("12", "12"),
        ("f", "f"),
        ("2f", "2f"),
        ("12T", "12T"),
    ],
)
def test_partial_commands_are_pending(keys, pending):
    engine = VimEngine(MemoryBuffer("abc def"), motion_keys())

    feed(engine, keys)

    assert engine.pending == pending
    assert buffer_of(engine).cursor == (0, 0)


def test_a_count_shows_along_with_a_longer_binding():
    keys = motion_keys()
    keys.set("gj", VimMotion.RIGHT)
    engine = VimEngine(MemoryBuffer("abcde"), keys)

    feed(engine, "3g")
    assert engine.pending == "3g"

    feed(engine, "j")
    assert engine.pending == ""
    assert buffer_of(engine).cursor == (0, 3)


@pytest.mark.parametrize("keys", ["2Q", "2q", "22Q"])
def test_a_key_that_fits_nothing_cancels_a_count_silently(keys):
    engine = VimEngine(MemoryBuffer("abc def", (0, 1)), motion_keys())

    for key in keys:
        assert engine.feed(key) is True

    assert engine.pending == ""
    assert buffer_of(engine).cursor == (0, 1)


def test_a_cancelled_count_does_not_carry_over():
    assert run_keys("a b c d e", (0, 0), "3Qw") == (0, 2)


def test_a_named_key_after_f_cancels_it_silently():
    engine = VimEngine(MemoryBuffer("abc def", (0, 1)), motion_keys())
    feed(engine, "2f")

    assert engine.feed("enter") is True

    assert engine.pending == ""
    assert buffer_of(engine).cursor == (0, 1)

    # It wasn't a jump, so there's nothing to repeat
    feed(engine, "h")
    assert buffer_of(engine).cursor == (0, 1)


@pytest.mark.parametrize("keys", ["2", "f", "2f", "t"])
def test_escape_cancels_a_partial_command_before_anything_else(keys):
    engine = VimEngine(MemoryBuffer("abc def", (0, 1)), motion_keys())
    feed(engine, keys)

    assert engine.feed("escape") is True
    assert engine.pending == ""
    assert buffer_of(engine).cursor == (0, 1)

    # And the next key starts afresh: `d` isn't a character to look for now
    assert engine.feed("escape") is False
    feed(engine, "ö")
    assert buffer_of(engine).cursor == (0, 2)


def test_pending_keys_do_not_survive_going_into_insert():
    engine = VimEngine(MemoryBuffer("abc"), motion_keys())
    feed(engine, "2")

    feed(engine, "i")

    assert engine.mode == MODE_INSERT
    assert engine.pending == ""


def test_digits_are_left_to_the_host_in_insert():
    engine = VimEngine(MemoryBuffer("abc"), motion_keys())
    feed(engine, "i")

    assert engine.feed("2") is False
    assert engine.pending == ""


def test_a_host_on_one_line_switches_off_the_line_motions():
    engine = VimEngine(MemoryBuffer("  a\n  b", (0, 0)), motion_keys(), multiline=False)

    assert engine.feed("ä") is False
    assert buffer_of(engine).cursor == (0, 0)


def test_a_remapped_word_motion_moves_with_its_key():
    keys = motion_keys()
    keys.remap({"w": "ß"})
    engine = VimEngine(MemoryBuffer("foo bar"), keys)

    feed(engine, "ß")
    assert buffer_of(engine).cursor == (0, 4)


# ---------------------------------------------------------------------------
# Showing where a character jump can go
# ---------------------------------------------------------------------------

JUMPS = "a b c b d\nq"


def after(keys: str, start: Tuple[int, int] = (0, 0)) -> VimEngine:
    engine = VimEngine(MemoryBuffer(JUMPS, start), motion_keys())
    feed(engine, keys)
    return engine


def test_nothing_is_shown_until_a_jump_starts():
    assert after("").find_view is None
    assert after("w").find_view is None


@pytest.mark.parametrize(
    "key, forward", [("f", True), ("t", True), ("F", False), ("T", False)]
)
def test_a_jump_waiting_for_its_character_shows_its_direction(key, forward):
    assert after(key, (0, 4)).find_view == FindView((0, 4), forward, ())


BOTH_BS = ((0, 2), (0, 6))


@pytest.mark.parametrize(
    "keys, start, view",
    [
        ("fb", (0, 0), FindView((0, 0), True, BOTH_BS)),
        ("Fb", (0, 8), FindView((0, 8), False, BOTH_BS)),
        # t and T show the cell they'd land on, not the character itself
        ("tb", (0, 0), FindView((0, 0), True, ((0, 1), (0, 5)))),
        ("Tb", (0, 8), FindView((0, 8), False, ((0, 3), (0, 7)))),
        # Only the way it's looking
        ("fb", (0, 4), FindView((0, 4), True, ((0, 6),))),
        ("Fb", (0, 4), FindView((0, 4), False, ((0, 2),))),
        # What's shown stays put as the cursor goes through it, either way
        ("fbh", (0, 0), FindView((0, 0), True, BOTH_BS)),
        ("fbhH", (0, 0), FindView((0, 0), True, BOTH_BS)),
        # Found nothing: still showing, with nowhere to go
        ("fz", (0, 0), FindView((0, 0), True, ())),
        # A count waiting for its repeat doesn't end it
        ("fb2", (0, 0), FindView((0, 0), True, BOTH_BS)),
        # Back past where it started: now everything, every way
        ("fbH", (0, 4), FindView((0, 4), None, BOTH_BS)),
        ("FbH", (0, 4), FindView((0, 4), None, BOTH_BS)),
        ("fbHh", (0, 4), FindView((0, 4), None, BOTH_BS)),
    ],
)
def test_a_jump_shows_where_it_can_go(keys, start, view):
    assert after(keys, start).find_view == view


@pytest.mark.parametrize(
    "start, keys, end",
    [
        ((0, 0), "fa", (0, 1)),
        ((0, 0), "2fa", (1, 1)),
        ((0, 0), "fah", (1, 1)),
        ((3, 0), "Fa", (1, 1)),
        ((3, 0), "2Fa", (0, 1)),
        ((3, 0), "Fah", (0, 1)),
        ((1, 1), "faH", (1, 1)),
        # An empty line has nothing to find, and doesn't stop the search
        ((1, 1), "fa", (3, 0)),
        # t lands on the line of the character it stops next to
        ((0, 1), "ta", (1, 0)),
        ((1, 0), "ta", (1, 0)),
        # An `a` at the very start of a line has no cell before it, so no t
        ((1, 1), "ta", (1, 1)),
        # And an `x` at the very end has none after it, so no T
        ((3, 1), "Tx", (0, 1)),
    ],
)
def test_jumps_go_across_lines(start, keys, end):
    assert run_keys("xa\nba\n\nabx", start, keys) == end


def test_a_jump_only_looks_at_the_rows_on_screen():
    buffer = MemoryBuffer("x\nxa\nxa\nxa")
    buffer.visible_rows = range(3)
    engine = VimEngine(buffer, motion_keys())

    feed(engine, "fa")
    assert engine.find_view == FindView((0, 0), True, ((1, 1), (2, 1)))

    feed(engine, "hh")
    assert buffer.cursor == (2, 1)


def test_a_host_on_one_line_only_looks_along_it():
    engine = VimEngine(MemoryBuffer("xa\nxa"), motion_keys(), multiline=False)

    feed(engine, "fa")
    assert engine.find_view == FindView((0, 0), True, ((0, 1),))

    feed(engine, "h")
    assert buffer_of(engine).cursor == (0, 1)


@pytest.mark.parametrize("key", ["j", "w", "ä", "Q", "i"])
def test_any_other_key_ends_the_showing(key):
    assert after("fb" + key).find_view is None


def test_a_new_jump_waiting_for_its_character_replaces_the_targets():
    assert after("fbF").find_view == FindView((0, 2), False, ())


def test_escape_ends_the_showing_before_anything_else():
    engine = after("fb")

    assert engine.feed("escape") is True
    assert engine.find_view is None
    assert engine.feed("escape") is False


def test_escape_ends_a_waiting_jump_and_its_showing():
    engine = after("f")

    assert engine.feed("escape") is True
    assert engine.find_view is None


def test_the_cursor_moving_some_other_way_ends_the_showing_for_good():
    engine = after("fb")
    buffer = buffer_of(engine)

    buffer.move_cursor(0, 0)
    assert engine.find_view is None

    buffer.move_cursor(0, 2)
    assert engine.find_view is None


def test_ending_the_showing_keeps_the_jump_for_repeating():
    engine = after("fb")
    feed(engine, "wh")

    # From `c`, on to the next `b`, showing from there
    assert buffer_of(engine).cursor == (0, 6)
    assert engine.find_view == FindView((0, 4), True, ((0, 6),))


TWENTY_LINES = "\n".join(f"line {n}" for n in range(20))


def test_half_page_keys_go_half_a_page_down_and_up():
    engine = engine_on(TWENTY_LINES, (7, 2))

    engine.feed("ctrl+d")
    assert buffer_of(engine).cursor == (12, 2)

    engine.feed("ctrl+u")
    engine.feed("ctrl+u")
    assert buffer_of(engine).cursor == (2, 2)


def test_a_count_on_a_half_page_key_multiplies_it():
    engine = engine_on(TWENTY_LINES)

    engine.feed("2")
    engine.feed("ctrl+d")

    assert buffer_of(engine).cursor == (10, 0)
    assert engine.pending == ""


def test_half_page_keys_stay_with_the_host_in_insert():
    engine = engine_on(TWENTY_LINES)
    feed(engine, "i")

    assert engine.feed("ctrl+d") is False
    assert buffer_of(engine).cursor == (0, 0)


@pytest.mark.parametrize(
    "start, keys, end",
    [
        ((3, 2), "gg", (0, 2)),
        ((3, 2), "G", (19, 2)),
        ((0, 0), "5G", (4, 0)),
        ((0, 0), "5gg", (4, 0)),
        ((0, 0), "12G", (11, 0)),
        ((5, 1), "99G", (19, 1)),
        ((5, 1), "99gg", (19, 1)),
    ],
)
def test_gg_and_g_go_to_the_ends_or_the_counted_line(start, keys, end):
    engine = engine_on(TWENTY_LINES, start)

    feed(engine, keys)

    assert buffer_of(engine).cursor == end
    assert engine.pending == ""


def test_a_lone_g_waits_and_shows_and_a_wrong_key_cancels_it():
    engine = engine_on(TWENTY_LINES, (3, 0))

    engine.feed("g")
    assert engine.pending == "g"
    assert buffer_of(engine).cursor == (3, 0)

    engine.feed("q")
    assert engine.pending == ""
    assert buffer_of(engine).cursor == (3, 0)


PARAGRAPHS = "one\ntwo\n\n\nthree\nfour\n\nfive!"


@pytest.mark.parametrize(
    "start, keys, end",
    [
        # The blank line under the paragraph
        ((0, 2), "}", (2, 0)),
        # From a blank line, past any more of them and the paragraph after
        ((2, 0), "}", (6, 0)),
        # No more blank lines: the last character of the note
        ((6, 0), "}", (7, 4)),
        ((7, 4), "}", (7, 4)),
        ((0, 0), "2}", (6, 0)),
        ((0, 0), "9}", (7, 4)),
        # The blank line above the paragraph
        ((5, 2), "{", (3, 0)),
        ((3, 0), "{", (0, 0)),
        ((1, 2), "{", (0, 0)),
        ((0, 0), "{", (0, 0)),
        ((7, 2), "2{", (3, 0)),
    ],
)
def test_braces_move_by_paragraph(start, keys, end):
    engine = engine_on(PARAGRAPHS, start)

    feed(engine, keys)

    assert buffer_of(engine).cursor == end


def test_a_line_of_spaces_does_not_end_a_paragraph():
    engine = engine_on("one\n   \ntwo\n\nthree")

    feed(engine, "}")

    assert buffer_of(engine).cursor == (3, 0)


def test_braces_on_a_note_with_no_blank_lines_go_to_its_ends():
    engine = engine_on("abc\ndef", (0, 1))

    feed(engine, "}")
    assert buffer_of(engine).cursor == (1, 2)

    feed(engine, "{")
    assert buffer_of(engine).cursor == (0, 0)


def test_zz_centres_the_view_and_leaves_the_cursor():
    engine = engine_on(TWENTY_LINES, (7, 2))

    engine.feed("z")
    assert engine.pending == "z"
    assert buffer_of(engine).centred == 0

    engine.feed("z")
    assert engine.pending == ""
    assert buffer_of(engine).centred == 1
    assert buffer_of(engine).cursor == (7, 2)


def test_k_and_l_go_by_screen_row_without_a_count_and_real_line_with_one():
    engine = engine_on(TWENTY_LINES, (9, 0))

    feed(engine, "l")
    feed(engine, "k")
    feed(engine, "3l")
    feed(engine, "2k")

    assert buffer_of(engine).vertical == [
        ("rows", 1),
        ("rows", -1),
        ("lines", 3),
        ("lines", -2),
    ]


@pytest.mark.parametrize(
    "keys", [["ctrl+u"], ["ctrl+d"], ["g", "g"], ["G"], ["{"], ["}"], ["z", "z"]]
)
def test_page_motions_do_nothing_on_a_single_line_host(keys):
    engine = engine_on("just the one", (0, 3), multiline=False)

    for key in keys:
        engine.feed(key)

    assert buffer_of(engine).cursor == (0, 3)
    assert buffer_of(engine).centred == 0
    assert engine.pending == ""


@pytest.mark.parametrize("key", ["ctrl+d", "G", "}"])
def test_a_single_line_host_is_left_those_keys(key):
    engine = engine_on("just the one", (0, 3), multiline=False)

    assert engine.feed(key) is False


def test_gx_asks_the_host_to_open_the_link_under_the_cursor():
    engine = engine_on("see https://example.com", (0, 6))

    feed(engine, "gx")

    assert buffer_of(engine).links_opened == 1
    assert buffer_of(engine).cursor == (0, 6)
    assert engine.pending == ""


def test_gf_asks_the_host_to_hand_over_to_its_files():
    engine = engine_on("abc", (0, 1))

    feed(engine, "gf")

    assert buffer_of(engine).files_picked == 1
    assert buffer_of(engine).cursor == (0, 1)
    assert engine.pending == ""


def test_a_count_does_not_repeat_gx_or_gf():
    engine = engine_on("abc")

    feed(engine, "3gx3gf")

    assert buffer_of(engine).links_opened == 1
    assert buffer_of(engine).files_picked == 1
    assert engine.pending == ""


def test_a_single_line_host_has_no_files_to_hand_over_but_can_open_a_link():
    engine = engine_on("abc", multiline=False)

    feed(engine, "gf")
    assert buffer_of(engine).files_picked == 0

    feed(engine, "gx")
    assert buffer_of(engine).links_opened == 1


# --- The delete operator ------------------------------------------------------


def delete_keys() -> VimKeymap:
    keys = motion_keys()
    keys.set("f", VimMotion.FIND_FORWARD)
    keys.set("F", VimMotion.FIND_BACKWARD)
    keys.set("t", VimMotion.TILL_FORWARD)
    keys.set("T", VimMotion.TILL_BACKWARD)
    keys.set("h", VimMotion.REPEAT_FIND)
    keys.set("H", VimMotion.REVERSE_FIND)
    keys.set("d", VimOperator.DELETE)
    keys.set("dd", VimCommand.DELETE_LINE)
    keys.set("D", VimCommand.DELETE_TO_LINE_END)
    keys.set("x", VimCommand.DELETE_CHAR)
    return keys


def deleting_on(
    text: str, cursor: Tuple[int, int] = (0, 0), **options
) -> VimEngine:
    return VimEngine(MemoryBuffer(text, cursor), delete_keys(), **options)


@pytest.mark.parametrize(
    "text, start, keys, after, cursor",
    [
        # Words
        ("foo bar baz", (0, 0), "dw", "bar baz", (0, 0)),
        ("foo bar baz", (0, 1), "dw", "fbar baz", (0, 1)),
        ("foo, bar", (0, 0), "dw", ", bar", (0, 0)),
        ("foo   bar", (0, 3), "dw", "foobar", (0, 3)),
        ("foo bar", (0, 0), "de", " bar", (0, 0)),
        ("foo bar", (0, 4), "db", "bar", (0, 0)),
        ("foo bar", (0, 5), "db", "foo ar", (0, 4)),
        # Characters on the line
        ("abcd", (0, 2), "dj", "acd", (0, 1)),
        ("abcd", (0, 2), "2dj", "cd", (0, 0)),
        ("abcd", (0, 1), "dö", "acd", (0, 1)),
        ("abcd", (0, 3), "dö", "abc", (0, 2)),
        ("abcd", (0, 1), "9dö", "a", (0, 0)),
        # The line's ends
        ("  abcd", (0, 4), "d=", "  cd", (0, 2)),
        ("  abcd", (0, 0), "d=", "abcd", (0, 0)),
        ("abc\ndef", (0, 1), "d_", "a\ndef", (0, 0)),
        ("abc\ndef\nghi", (0, 1), "2d_", "a\nghi", (0, 0)),
        # Character jumps, to and till, both ways
        ("ab,cd,ef", (0, 0), "df,", "cd,ef", (0, 0)),
        ("ab,cd,ef", (0, 0), "dt,", ",cd,ef", (0, 0)),
        ("ab,cd,ef", (0, 7), "dF,", "ab,cdf", (0, 5)),
        ("ab,cd,ef", (0, 7), "dT,", "ab,cd,f", (0, 6)),
        ("ab,cd,ef", (0, 0), "2df,", "ef", (0, 0)),
        ("a,b", (0, 0), "dt,", ",b", (0, 0)),
        # Lines whole
        ("a\nb\nc", (0, 0), "dl", "c", (0, 0)),
        ("a\nb\nc", (2, 0), "dk", "a", (0, 0)),
        ("a\nb\nc\nd", (0, 0), "2dl", "d", (0, 0)),
        ("a\nb\nc", (1, 0), "9dl", "a", (0, 0)),
        ("a\n  b\nc", (0, 0), "dä", "c", (0, 0)),
        ("a\n  b\nc", (1, 0), "dü", "c", (0, 0)),
        ("a\nb\nc", (1, 0), "dgg", "c", (0, 0)),
        ("a\nb\nc", (1, 0), "dG", "a", (0, 0)),
        ("a\nb\nc\nd", (3, 0), "d2gg", "a", (0, 0)),
        # Paragraphs
        ("ab cd\nef\n\ngh", (0, 3), "d}", "ab \n\ngh", (0, 2)),
        ("ab\n\ncd ef", (2, 3), "d{", "ab\nef", (1, 0)),
        # The last paragraph has no blank line to stop short of
        ("ab cd", (0, 3), "d}", "ab ", (0, 2)),
    ],
)
def test_d_takes_any_motion(text, start, keys, after, cursor):
    engine = deleting_on(text, start)

    feed(engine, keys)

    assert buffer_of(engine).text == after
    assert buffer_of(engine).cursor == cursor
    assert engine.mode == MODE_NORMAL
    assert engine.pending == ""


def test_half_a_page_is_deleted_in_lines_not_rows():
    engine = deleting_on("\n".join("abcdefgh"), (1, 0))
    buffer_of(engine).half_page = 2
    engine.keys.set("<ctrl+d>", VimMotion.HALF_PAGE_DOWN)
    engine.keys.set("<ctrl+u>", VimMotion.HALF_PAGE_UP)

    for key in ("d", "ctrl+d"):
        engine.feed(key)

    assert buffer_of(engine).text == "\n".join("aefgh")
    assert buffer_of(engine).vertical == []

    buffer_of(engine).move_cursor(3, 0)

    for key in ("d", "ctrl+u"):
        engine.feed(key)

    assert buffer_of(engine).text == "\n".join("ah")


@pytest.mark.parametrize(
    "keys, after",
    [
        ("2d3w", "g h"),
        ("3d2w", "g h"),
        ("6dw", "g h"),
        ("d6w", "g h"),
        ("2d3e", " h"),
    ],
)
def test_counts_multiply(keys, after):
    engine = deleting_on("a b c d e f g h")

    feed(engine, keys)

    assert buffer_of(engine).text == after


def test_a_motion_that_finds_nothing_deletes_nothing():
    engine = deleting_on("abc def", (0, 1))

    feed(engine, "dfz")
    assert buffer_of(engine).text == "abc def"
    assert buffer_of(engine).cursor == (0, 1)

    feed(engine, "d2f ")
    assert buffer_of(engine).text == "abc def"

    assert engine.register is None
    assert engine.pending == ""


def test_a_vertical_motion_off_the_note_deletes_nothing():
    engine = deleting_on("a\nb")

    feed(engine, "dk")
    assert buffer_of(engine).text == "a\nb"

    buffer_of(engine).move_cursor(1, 0)
    feed(engine, "dl")
    assert buffer_of(engine).text == "a\nb"

    feed(engine, "dä")
    assert buffer_of(engine).text == "a\nb"
    assert engine.register is None


def test_dw_on_a_line_s_last_word_keeps_the_line_break():
    engine = deleting_on("foo bar\nbaz", (0, 4))

    feed(engine, "dw")

    assert buffer_of(engine).text == "foo \nbaz"
    assert buffer_of(engine).cursor == (0, 3)


def test_dw_on_the_note_s_last_word_takes_it_all():
    engine = deleting_on("foo bar", (0, 4))

    feed(engine, "dw")

    assert buffer_of(engine).text == "foo "


def test_a_counted_dw_crosses_lines_but_stops_at_the_last_one():
    engine = deleting_on("a b\nc d\ne f")

    feed(engine, "3dw")
    assert buffer_of(engine).text == "d\ne f"

    feed(engine, "9dw")
    assert buffer_of(engine).text == ""


def test_dw_on_an_empty_line_takes_the_line():
    engine = deleting_on("a\n\nb", (1, 0))

    feed(engine, "dw")

    assert buffer_of(engine).text == "a\nb"
    assert engine.register == Register("", linewise=True)


def test_an_exclusive_motion_ending_at_a_line_s_start_stops_on_the_line_before():
    # Neither the line break nor anything of the next line is in `d}` from here
    engine = deleting_on("  ab cd\nef\n\ngh", (0, 5))

    feed(engine, "d}")

    assert buffer_of(engine).text == "  ab \n\ngh"
    assert engine.register == Register("cd\nef", linewise=False)


def test_a_paragraph_from_its_start_is_deleted_as_whole_lines():
    engine = deleting_on("ab\ncd\n\nef")

    feed(engine, "d}")

    assert buffer_of(engine).text == "\nef"
    assert engine.register == Register("ab\ncd", linewise=True)


def test_db_from_a_line_s_start_leaves_the_line_break():
    engine = deleting_on("foo bar\nbaz", (1, 0))

    feed(engine, "db")

    assert buffer_of(engine).text == "foo \nbaz"


def test_a_character_jump_reaches_across_visible_lines():
    engine = deleting_on("ab\ncd,ef", (0, 1))

    feed(engine, "df,")

    assert buffer_of(engine).text == "aef"
    assert buffer_of(engine).cursor == (0, 1)
    assert engine.register == Register("b\ncd,", linewise=False)


def test_d_repeats_a_character_jump_and_takes_its_direction():
    engine = deleting_on("a,b,c,d", (0, 0))

    feed(engine, "f,")
    assert buffer_of(engine).cursor == (0, 1)

    feed(engine, "dh")
    assert buffer_of(engine).text == "ac,d"
    assert buffer_of(engine).cursor == (0, 1)

    # Backward is exclusive, as `F` is: the cursor's own character stays
    engine = deleting_on("a,b,c,d", (0, 0))
    feed(engine, "f,f,")
    assert buffer_of(engine).cursor == (0, 3)

    feed(engine, "dH")
    assert buffer_of(engine).text == "a,c,d"
    assert buffer_of(engine).cursor == (0, 1)


def test_dh_before_any_jump_deletes_nothing():
    engine = deleting_on("a,b")

    feed(engine, "dh")

    assert buffer_of(engine).text == "a,b"
    assert engine.pending == ""


def test_a_deleting_jump_can_be_repeated_as_a_plain_one():
    engine = deleting_on("a,b,c")

    feed(engine, "df,h")

    assert buffer_of(engine).text == "b,c"
    assert buffer_of(engine).cursor == (0, 1)


def test_nothing_of_a_character_jump_is_left_on_show_after_a_delete():
    engine = deleting_on("a,b,c")

    feed(engine, "d")
    engine.feed("f")
    assert engine.find_view is not None

    engine.feed(",")
    assert engine.find_view is None


@pytest.mark.parametrize(
    "start, keys, after, cursor",
    [
        ((0, 0), "dd", "b\nc\nd", (0, 0)),
        ((1, 0), "dd", "a\nc\nd", (1, 0)),
        ((3, 0), "dd", "a\nb\nc", (2, 0)),
        ((0, 0), "3dd", "d", (0, 0)),
        ((0, 0), "d3d", "d", (0, 0)),
        ((1, 0), "2d2d", "a", (0, 0)),
        ((2, 0), "9dd", "a\nb", (1, 0)),
    ],
)
def test_dd_deletes_whole_lines(start, keys, after, cursor):
    engine = deleting_on("a\nb\nc\nd", start)

    feed(engine, keys)

    assert buffer_of(engine).text == after
    assert buffer_of(engine).cursor == cursor


def test_dd_on_the_only_line_leaves_an_empty_note():
    engine = deleting_on("abc", (0, 2))

    feed(engine, "dd")

    assert buffer_of(engine).text == ""
    assert buffer_of(engine).line_count == 1
    assert buffer_of(engine).cursor == (0, 0)


def test_a_deleted_line_leaves_the_cursor_in_its_column_as_lazyvim_does():
    engine = deleting_on("abcdef\nghijkl\nmn", (0, 3))

    feed(engine, "dd")
    assert buffer_of(engine).cursor == (0, 3)

    feed(engine, "dd")
    assert buffer_of(engine).cursor == (0, 1)


@pytest.mark.parametrize(
    "start, keys, after, cursor",
    [
        ((0, 2), "D", "ab\nghi\njkl", (0, 1)),
        ((0, 0), "D", "\nghi\njkl", (0, 0)),
        ((0, 2), "2D", "ab\njkl", (0, 1)),
        ((0, 2), "x", "abde\nghi\njkl", (0, 2)),
        ((0, 4), "x", "abcd\nghi\njkl", (0, 3)),
        ((0, 1), "2x", "ade\nghi\njkl", (0, 1)),
        ((0, 3), "9x", "abc\nghi\njkl", (0, 2)),
    ],
)
def test_big_d_and_x(start, keys, after, cursor):
    engine = deleting_on("abcde\nghi\njkl", start)

    feed(engine, keys)

    assert buffer_of(engine).text == after
    assert buffer_of(engine).cursor == cursor


@pytest.mark.parametrize("keys", ["x", "D", "d_"])
def test_on_an_empty_line_the_small_deletes_join_nothing(keys):
    engine = deleting_on("a\n\nb", (1, 0))

    feed(engine, keys)

    assert buffer_of(engine).text == "a\n\nb"
    assert buffer_of(engine).cursor == (1, 0)
    assert engine.register is None


@pytest.mark.parametrize(
    "start, keys, register",
    [
        ((0, 0), "dw", Register("ab ", linewise=False)),
        ((0, 3), "d_", Register("cd", linewise=False)),
        ((0, 3), "D", Register("cd", linewise=False)),
        ((0, 3), "x", Register("c", linewise=False)),
        ((0, 3), "db", Register("ab ", linewise=False)),
        ((0, 0), "dd", Register("ab cd", linewise=True)),
        ((0, 0), "2dd", Register("ab cd\nef", linewise=True)),
        ((0, 0), "dl", Register("ab cd\nef", linewise=True)),
    ],
)
def test_a_delete_fills_the_register(start, keys, register):
    engine = deleting_on("ab cd\nef\ngh", start)

    assert engine.register is None
    feed(engine, keys)

    assert engine.register == register


def test_escape_cancels_a_pending_operator_and_only_that():
    engine = deleting_on("abc def")

    feed(engine, "2d3")
    assert engine.pending == "2d3"

    assert engine.feed("escape") is True
    assert engine.pending == ""

    feed(engine, "w")
    assert buffer_of(engine).text == "abc def"
    assert buffer_of(engine).cursor == (0, 4)

    # With nothing pending it's the host's again
    assert engine.feed("escape") is False


def test_escape_cancels_a_character_jump_an_operator_is_waiting_on():
    engine = deleting_on("abc def")

    feed(engine, "df")
    assert engine.pending == "df"

    engine.feed("escape")
    assert engine.pending == ""

    feed(engine, "d")
    assert engine.pending == "d"


@pytest.mark.parametrize("keys", ["dq", "d0", "dgq", "dzq", "di", "dx", "2d3q"])
def test_an_invalid_key_cancels_an_operator_silently(keys):
    engine = deleting_on("abc def")

    feed(engine, keys)

    assert buffer_of(engine).text == "abc def"
    assert buffer_of(engine).cursor == (0, 0)
    assert engine.mode == MODE_NORMAL
    assert engine.pending == ""
    assert engine.register is None


def test_a_key_without_a_character_cancels_too_and_stays_with_the_engine():
    engine = deleting_on("abc def")

    feed(engine, "d")

    assert engine.feed("enter") is True
    assert engine.pending == ""
    assert buffer_of(engine).text == "abc def"


def test_a_command_key_after_an_operator_does_not_run():
    engine = deleting_on("abc")
    engine.keys.set("gx", VimCommand.OPEN_LINK)
    engine.keys.set("zz", VimCommand.CENTER_VIEW)

    feed(engine, "dgx")
    feed(engine, "dzz")
    feed(engine, "di")

    assert buffer_of(engine).links_opened == 0
    assert buffer_of(engine).centred == 0
    assert engine.mode == MODE_NORMAL


def test_the_pending_keys_build_up_as_typed():
    engine = deleting_on("abc def")
    seen = []

    for key in "2d3f":
        engine.feed(key)
        seen.append(engine.pending)

    assert seen == ["2", "2d", "2d3", "2d3f"]


def test_an_operator_with_no_doubled_binding_still_takes_motions():
    keys = delete_keys()
    keys.remap({"d": "q"})
    engine = VimEngine(MemoryBuffer("abc def"), keys)

    feed(engine, "qw")

    assert buffer_of(engine).text == "def"


def test_the_doubled_form_is_a_binding_of_its_own():
    keys = delete_keys()
    keys.set("dq", VimCommand.DELETE_LINE)
    engine = VimEngine(MemoryBuffer("abc\ndef"), keys)

    feed(engine, "dq")

    assert buffer_of(engine).text == "def"


def test_a_single_line_host_has_no_line_deletes():
    engine = deleting_on("abc def", multiline=False)

    feed(engine, "dd")
    assert buffer_of(engine).text == "abc def"
    assert engine.pending == ""

    feed(engine, "dl")
    assert buffer_of(engine).text == "abc def"
    assert engine.pending == ""

    feed(engine, "dw")
    assert buffer_of(engine).text == "def"
