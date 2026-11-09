"""
The vim engine on its own: keys go in, text, cursor and mode come out

Nothing here knows about Textual. The engine drives a buffer held in memory, as
any host would drive it.
"""

import ast
import re
from pathlib import Path
from typing import Dict, List, Optional, Set, Tuple

import pytest

import todooit.vim_engine
from todooit.vim_engine import (
    DESCRIPTION_ACTIONS,
    MODE_FLASH,
    MODE_INSERT,
    MODE_NORMAL,
    MODE_VISUAL,
    MODE_VISUAL_LINE,
    VIM_FLASH_ALPHABET,
    FindView,
    Register,
    RegisterMemory,
    Search,
    SearchMemory,
    VimCommand,
    VimEngine,
    VimFlashView,
    VimKeymap,
    VimMotion,
    VimOperator,
    VimTextObject,
    YankedRange,
)
from todooit.vim_engine.engine import LINE_ONLY


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
        self.helps_shown = 0
        self.undo_steps: List[Tuple[List[str], Tuple[int, int], List[str]]] = []
        self.redo_steps: List[Tuple[List[str], Tuple[int, int], List[str]]] = []
        self.step_start: Optional[Tuple[List[str], Tuple[int, int]]] = None
        self.step_edited = False
        self.reports: List[str] = []
        self.prompts_shown = 0
        self.clipboard = ""
        self.clipboard_reads = 0
        self.clipboard_pastes: List[str] = []
        # Rows drawn differently: the text, and the stored column behind each of
        # its columns and its end
        self.drawn: Dict[int, Tuple[str, List[int]]] = {}
        # What's shown selected: from where, to the cursor, and whether as lines
        self.selected: Optional[Tuple[Tuple[int, int], Tuple[int, int], bool]] = None

    @property
    def line_count(self) -> int:
        return len(self.lines)

    def line(self, row: int) -> str:
        return self.lines[row]

    def drawn_line(self, row: int) -> str:
        return self.drawn[row][0] if row in self.drawn else self.lines[row]

    def stored_column(self, row: int, column: int) -> int:
        return self.drawn[row][1][column] if row in self.drawn else column

    def move_cursor(self, row: int, column: int) -> None:
        self.cursor = (row, column)
        self.selected = None

    def select(self, anchor: Tuple[int, int], linewise: bool) -> None:
        self.selected = (anchor, self.cursor, linewise)

    def replace(
        self, start: Tuple[int, int], end: Tuple[int, int], text: str
    ) -> None:
        head = self.lines[start[0]][: start[1]]
        tail = self.lines[end[0]][end[1] :]
        self.lines[start[0] : end[0] + 1] = (head + text + tail).split("\n")
        self.step_edited = True

    def _go_down(self, delta: int) -> None:
        self.selected = None
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

    def show_help(self) -> None:
        self.helps_shown += 1

    def list_prefix(self, row: int) -> str:
        found = re.match(r"(> )?\s*([-*] |\d+\. )?", self.lines[row])
        assert found is not None
        return found.group() if found.group(1) or found.group(2) else ""

    def nesting_start(self, row: int) -> int:
        found = re.match(r"[ \t]*> ", self.lines[row])
        return found.end() if found else 0

    def mode_changed(self, mode: str) -> None:
        self.modes.append(mode)

    def begin_undo_step(self) -> None:
        self.step_start = (list(self.lines), self.cursor)
        self.step_edited = False

    def end_undo_step(self) -> None:
        assert self.step_start is not None
        lines, cursor = self.step_start
        self.step_start = None

        if self.step_edited:
            self.undo_steps.append((lines, cursor, list(self.lines)))
            self.redo_steps.clear()

    def undo(self) -> None:
        if self.undo_steps:
            step = self.undo_steps.pop()
            self.redo_steps.append(step)
            self.lines, self.cursor = list(step[0]), step[1]

    def redo(self) -> None:
        if self.redo_steps:
            step = self.redo_steps.pop()
            self.undo_steps.append(step)
            self.lines, self.cursor = list(step[2]), step[1]

    def report(self, message: str) -> None:
        self.reports.append(message)

    def prompt_changed(self) -> None:
        self.prompts_shown += 1

    def copy_to_clipboard(self, text: str) -> None:
        self.clipboard = text

    def clipboard_text(self) -> str:
        self.clipboard_reads += 1
        return self.clipboard

    def paste_clipboard_text(self, text: str) -> None:
        self.clipboard_pastes.append(text)
        row, column = self.cursor
        self.replace(self.cursor, self.cursor, text)
        lines = text.split("\n")
        self.cursor = (
            row + len(lines) - 1,
            len(lines[-1]) + (column if len(lines) == 1 else 0),
        )

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
    keys.set("?", VimCommand.SEARCH)
    keys.set("*", VimCommand.SEARCH_WORD)
    keys.set("n", VimMotion.SEARCH_NEXT)
    keys.set("N", VimMotion.SEARCH_PREVIOUS)
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


@pytest.mark.parametrize(
    "text, start, keys, end",
    [
        ("  ab cd", (0, 5), "0", (0, 0)),
        ("  ab cd", (0, 0), "0", (0, 0)),
    ],
)
def test_line_start_goes_to_the_first_column(text, start, keys, end):
    vim_keys = motion_keys()
    vim_keys.set("0", VimMotion.LINE_START)
    engine = VimEngine(MemoryBuffer(text, start), vim_keys)
    feed(engine, keys)

    assert buffer_of(engine).cursor == end
    assert engine.pending == ""


def test_deleting_to_the_line_start_takes_the_indent_too():
    engine = deleting_on("  ab cd", (0, 5))
    engine.keys.set("0", VimMotion.LINE_START)
    feed(engine, "d0")

    assert buffer_of(engine).text == "cd"
    assert buffer_of(engine).cursor == (0, 0)


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


# --- Into INSERT, and the change operator --------------------------------------


def change_keys() -> VimKeymap:
    keys = delete_keys()
    keys.set("a", VimCommand.INSERT_AFTER)
    keys.set("I", VimCommand.INSERT_FIRST_NON_BLANK)
    keys.set("A", VimCommand.INSERT_LINE_END)
    keys.set("o", VimCommand.OPEN_BELOW)
    keys.set("O", VimCommand.OPEN_ABOVE)
    keys.set("gi", VimCommand.INSERT_AT_LAST)
    keys.set("c", VimOperator.CHANGE)
    keys.set("cc", VimCommand.CHANGE_LINE)
    keys.set("C", VimCommand.CHANGE_TO_LINE_END)
    keys.set("r", VimCommand.REPLACE_CHAR)
    return keys


def changing_on(
    text: str, cursor: Tuple[int, int] = (0, 0), **options
) -> VimEngine:
    return VimEngine(MemoryBuffer(text, cursor), change_keys(), **options)


@pytest.mark.parametrize(
    "text, start, keys, cursor",
    [
        ("foo", (0, 1), "i", (0, 1)),
        ("foo", (0, 1), "a", (0, 2)),
        # After the last character is where only INSERT can stand
        ("foo", (0, 2), "a", (0, 3)),
        ("", (0, 0), "a", (0, 0)),
        ("  foo", (0, 4), "I", (0, 2)),
        ("  foo", (0, 0), "A", (0, 5)),
        ("- foo", (0, 3), "I", (0, 0)),
        ("", (0, 0), "A", (0, 0)),
        ("", (0, 0), "I", (0, 0)),
        # INSERT can stand after the blanks, as NORMAL can't
        ("   ", (0, 0), "I", (0, 3)),
    ],
)
def test_the_ways_into_insert_put_the_cursor_where_they_say(
    text, start, keys, cursor
):
    engine = changing_on(text, start)

    feed(engine, keys)

    assert engine.mode == MODE_INSERT
    assert buffer_of(engine).cursor == cursor
    assert buffer_of(engine).text == text


@pytest.mark.parametrize(
    "text, start, keys, after, cursor",
    [
        ("foo\nbar", (0, 1), "o", "foo\n\nbar", (1, 0)),
        ("foo\nbar", (1, 1), "O", "foo\n\nbar", (1, 0)),
        ("foo", (0, 0), "o", "foo\n", (1, 0)),
        ("foo", (0, 0), "O", "\nfoo", (0, 0)),
        # The list goes on, above as well as below
        ("- foo", (0, 3), "o", "- foo\n- ", (1, 2)),
        ("- foo", (0, 3), "O", "- \n- foo", (0, 2)),
        ("  * foo", (0, 3), "o", "  * foo\n  * ", (1, 4)),
        ("> - foo", (0, 3), "O", "> - \n> - foo", (0, 4)),
        ("> foo", (0, 3), "o", "> foo\n> ", (1, 2)),
        ("1. foo", (0, 3), "o", "1. foo\n1. ", (1, 3)),
        # A bare indent is no list, and `enter` doesn't carry it either
        ("  foo", (0, 3), "o", "  foo\n", (1, 0)),
    ],
)
def test_opening_a_line_carries_the_list_prefix(text, start, keys, after, cursor):
    engine = changing_on(text, start)

    feed(engine, keys)

    assert engine.mode == MODE_INSERT
    assert buffer_of(engine).text == after
    assert buffer_of(engine).cursor == cursor


@pytest.mark.parametrize(
    "text, start, keys, after, cursor, register",
    [
        # Words: `cw` stops at the end of the word, where `dw` goes on to the next
        ("foo bar", (0, 0), "cw", " bar", (0, 0), "foo"),
        ("foo bar", (0, 1), "cw", "f bar", (0, 1), "oo"),
        ("foo bar", (0, 2), "cw", "fo bar", (0, 2), "o"),
        ("foo, bar", (0, 0), "cw", ", bar", (0, 0), "foo"),
        ("foo", (0, 0), "cw", "", (0, 0), "foo"),
        # On blanks it takes those, as `dw` does
        ("foo   bar", (0, 3), "cw", "foobar", (0, 3), "   "),
        # Counts stop at the end of the last word too
        ("a b c d", (0, 0), "c2w", " c d", (0, 0), "a b"),
        ("a b c d", (0, 0), "2cw", " c d", (0, 0), "a b"),
        # Starting on blanks, a count goes as far as it does for `d`
        ("a  b c", (0, 1), "2cw", "ac", (0, 1), "  b "),
        ("a b c d e", (0, 0), "2c2w", " e", (0, 0), "a b c d"),
        # The other motions go as far as they do for `d`
        ("foo bar", (0, 0), "ce", " bar", (0, 0), "foo"),
        ("foo bar", (0, 4), "cb", "bar", (0, 0), "foo "),
        ("foo, bar", (0, 0), "ct,", ", bar", (0, 0), "foo"),
        ("foo, bar", (0, 0), "cf,", " bar", (0, 0), "foo,"),
        ("foo bar", (0, 5), "cFo", "foar", (0, 2), "o b"),
        ("  foo", (0, 3), "c=", "  oo", (0, 2), "f"),
        ("foo bar", (0, 4), "c_", "foo ", (0, 4), "bar"),
        ("abc", (0, 1), "cö", "ac", (0, 1), "b"),
        ("abc", (0, 2), "cö", "ab", (0, 2), "c"),
        ("abc", (0, 2), "cj", "ac", (0, 1), "b"),
        # `C` is `c` to the end of the line
        ("foo bar", (0, 4), "C", "foo ", (0, 4), "bar"),
        ("foo\nbar", (0, 1), "C", "f\nbar", (0, 1), "oo"),
        ("", (0, 0), "C", "", (0, 0), None),
    ],
)
def test_change_takes_the_text_and_goes_into_insert_at_its_place(
    text, start, keys, after, cursor, register
):
    engine = changing_on(text, start)

    feed(engine, keys)

    assert engine.mode == MODE_INSERT
    assert buffer_of(engine).text == after
    assert buffer_of(engine).cursor == cursor
    assert engine.pending == ""

    if register is not None:
        assert engine.register == Register(register, linewise=False)


@pytest.mark.parametrize(
    "text, start, keys, after, cursor, register",
    [
        # Indent and marker stay, the cursor goes after them
        ("- foo", (0, 3), "cc", "- ", (0, 2), "- foo"),
        ("  - foo", (0, 5), "cc", "  - ", (0, 4), "  - foo"),
        ("1. foo", (0, 4), "cc", "1. ", (0, 3), "1. foo"),
        ("> - foo", (0, 0), "cc", "> - ", (0, 4), "> - foo"),
        ("> foo", (0, 3), "cc", "> ", (0, 2), "> foo"),
        # The indent behind a quote or a marker is kept with it
        (">   foo", (0, 5), "cc", ">   ", (0, 4), ">   foo"),
        ("   ", (0, 1), "cc", "   ", (0, 3), "   "),
        # A bare indent counts, and nothing at all is fine
        ("    foo", (0, 5), "cc", "    ", (0, 4), "    foo"),
        ("foo", (0, 2), "cc", "", (0, 0), "foo"),
        ("", (0, 0), "cc", "", (0, 0), ""),
        ("- ", (0, 1), "cc", "- ", (0, 2), "- "),
        # Other lines are left alone
        ("a\n- foo\nb", (1, 3), "cc", "a\n- \nb", (1, 2), "- foo"),
        # A count, and motions over whole lines, leave one line in their place
        ("- a\n- b\n- c", (0, 0), "2cc", "- \n- c", (0, 2), "- a\n- b"),
        ("- a\n- b", (0, 0), "5cc", "- ", (0, 2), "- a\n- b"),
        ("- a\n- b\n- c", (0, 0), "cl", "- \n- c", (0, 2), "- a\n- b"),
        ("- a\n- b\n- c", (2, 0), "ck", "- a\n- ", (1, 2), "- b\n- c"),
        ("  a\nb\nc", (0, 0), "cG", "  ", (0, 2), "  a\nb\nc"),
        ("a\nb", (1, 0), "cgg", "", (0, 0), "a\nb"),
    ],
)
def test_changing_whole_lines_keeps_the_first_ones_indent_and_marker(
    text, start, keys, after, cursor, register
):
    engine = changing_on(text, start)

    feed(engine, keys)

    assert engine.mode == MODE_INSERT
    assert buffer_of(engine).text == after
    assert buffer_of(engine).cursor == cursor
    assert engine.register == Register(register, linewise=True)


def test_change_from_a_lines_start_to_a_blank_line_is_whole_lines():
    engine = changing_on("- a\n- b\n\nc")

    feed(engine, "c}")

    assert engine.mode == MODE_INSERT
    assert buffer_of(engine).text == "- \n\nc"
    assert buffer_of(engine).cursor == (0, 2)


@pytest.mark.parametrize(
    "text, start, keys",
    [
        # Nothing to find
        ("foo", (0, 0), "cfz"),
        ("foo", (0, 0), "ctz"),
        # No line to go to
        ("foo", (0, 0), "cl"),
        ("foo", (0, 0), "ck"),
        # Nowhere to go back to
        ("foo", (0, 0), "cb"),
        ("foo", (0, 0), "cj"),
        ("foo", (0, 0), "c{"),
    ],
)
def test_a_change_whose_motion_fails_stays_in_normal(text, start, keys):
    engine = changing_on(text, start)

    feed(engine, keys)

    assert engine.mode == MODE_NORMAL
    assert buffer_of(engine).text == text
    assert buffer_of(engine).cursor == start
    assert engine.pending == ""


@pytest.mark.parametrize(
    "text, start, keys",
    [
        # These can't fail, so standing there already is only nothing to take
        ("  foo", (0, 2), "c="),
        ("", (0, 0), "c_"),
        ("", (0, 0), "cw"),
    ],
)
def test_a_change_with_nothing_to_take_still_goes_into_insert(text, start, keys):
    engine = changing_on(text, start)

    feed(engine, keys)

    assert engine.mode == MODE_INSERT
    assert buffer_of(engine).text == text
    assert buffer_of(engine).cursor == start


def test_escape_cancels_a_pending_change():
    engine = changing_on("foo bar")

    feed(engine, "2c")
    assert engine.pending == "2c"

    assert engine.feed("escape") is True

    assert engine.pending == ""
    assert engine.mode == MODE_NORMAL
    assert buffer_of(engine).text == "foo bar"


def test_a_change_leaves_what_it_took_in_the_register_and_escape_comes_back():
    engine = changing_on("foo bar")

    feed(engine, "cw")
    engine.feed("escape")

    assert engine.mode == MODE_NORMAL
    assert engine.register == Register("foo", linewise=False)
    assert buffer_of(engine).cursor == (0, 0)


@pytest.mark.parametrize(
    "text, start, keys, after, cursor",
    [
        ("abc", (0, 1), "rx", "axc", (0, 1)),
        ("abc", (0, 2), "rx", "abx", (0, 2)),
        # A count replaces that many, and leaves the cursor on the last of them
        ("abcd", (0, 0), "3rx", "xxxd", (0, 2)),
        # Or none, if there aren't that many
        ("abc", (0, 1), "3rx", "abc", (0, 1)),
        # Nothing to replace
        ("", (0, 0), "rx", "", (0, 0)),
        # Bound to something else or not, the next key is what's typed
        ("abc", (0, 0), "rd", "dbc", (0, 0)),
        ("abc", (0, 0), "r ", " bc", (0, 0)),
        ("abc", (0, 0), "r5", "5bc", (0, 0)),
    ],
)
def test_r_replaces_characters_and_stays_in_normal(text, start, keys, after, cursor):
    engine = changing_on(text, start)

    feed(engine, keys)

    assert engine.mode == MODE_NORMAL
    assert buffer_of(engine).text == after
    assert buffer_of(engine).cursor == cursor
    assert engine.pending == ""
    assert engine.register is None


def test_r_shows_as_pending_and_escape_or_a_named_key_cancels_it():
    engine = changing_on("abc")

    feed(engine, "2r")
    assert engine.pending == "2r"

    assert engine.feed("escape") is True
    assert engine.pending == ""
    assert engine.mode == MODE_NORMAL

    feed(engine, "r")
    assert engine.feed("enter") is True
    assert engine.pending == ""
    assert buffer_of(engine).text == "abc"


def test_gi_returns_to_where_insert_was_left():
    engine = changing_on("foo\nbar", (0, 3))

    feed(engine, "i")
    engine.feed("escape")
    assert buffer_of(engine).cursor == (0, 2)

    buffer_of(engine).move_cursor(1, 1)
    feed(engine, "gi")

    assert engine.mode == MODE_INSERT
    assert buffer_of(engine).cursor == (0, 3)


def test_gi_with_no_insert_yet_inserts_at_the_cursor():
    engine = changing_on("foo\nbar", (1, 1))

    feed(engine, "gi")

    assert engine.mode == MODE_INSERT
    assert buffer_of(engine).cursor == (1, 1)


def test_gi_lands_on_the_text_there_is_now():
    engine = changing_on("foo\nbar", (1, 3))

    feed(engine, "i")
    engine.feed("escape")
    feed(engine, "dd")
    feed(engine, "gi")
    assert buffer_of(engine).cursor == (0, 3)

    engine.feed("escape")
    buffer_of(engine).lines[0] = "x"
    feed(engine, "gi")
    assert buffer_of(engine).cursor == (0, 1)


def test_gi_is_kept_per_engine_so_a_new_window_starts_over():
    first = changing_on("foo", (0, 2))
    feed(first, "i")
    first.feed("escape")

    second = changing_on("foo", (0, 0))
    feed(second, "gi")

    assert buffer_of(second).cursor == (0, 0)


def test_a_host_with_one_line_has_no_lines_to_open():
    engine = changing_on("abc", multiline=False)

    feed(engine, "o")
    assert engine.mode == MODE_NORMAL

    feed(engine, "O")
    assert engine.mode == MODE_NORMAL
    assert buffer_of(engine).text == "abc"

    feed(engine, "cc")
    assert engine.mode == MODE_INSERT
    assert buffer_of(engine).text == ""


def test_the_keys_after_an_insert_are_left_to_the_host():
    engine = changing_on("abc")

    feed(engine, "cw")

    assert engine.feed("x") is False
    assert buffer_of(engine).text == ""


# --- Undo and redo --------------------------------------------------------------


def undoing_on(text: str, cursor: Tuple[int, int] = (0, 0), **options) -> VimEngine:
    keys = change_keys()
    keys.set("u", VimCommand.UNDO)
    keys.set("<ctrl+r>", VimCommand.REDO)

    return VimEngine(MemoryBuffer(text, cursor), keys, **options)


def typing(engine: VimEngine, text: str) -> None:
    """What the host does with the keys the engine leaves to it in INSERT."""

    buffer = buffer_of(engine)
    row, column = buffer.cursor

    for char in text:
        assert engine.feed(char) is False
        buffer.replace((row, column), (row, column), char)
        column += 1
        buffer.move_cursor(row, column)


def test_u_takes_back_a_command_and_ctrl_r_puts_it_back():
    engine = undoing_on("one two", (0, 4))
    buffer = buffer_of(engine)

    feed(engine, "x")
    assert buffer.text == "one wo"

    feed(engine, "u")
    assert buffer.text == "one two"
    assert buffer.cursor == (0, 4)
    assert engine.mode == MODE_NORMAL

    assert engine.feed("ctrl+r") is True
    assert buffer.text == "one wo"
    assert buffer.cursor == (0, 4)
    assert engine.mode == MODE_NORMAL


@pytest.mark.parametrize(
    "text, keys, after",
    [
        ("a b c d e", "3x", " c d e"),
        ("a b c d e", "dw", "b c d e"),
        ("a b c d e", "2dw", "c d e"),
        ("a b c d e", "rZ", "Z b c d e"),
        ("one\ntwo\nthree", "2dd", "three"),
        ("a b c d e", "dfc", " d e"),
    ],
)
def test_each_normal_command_is_one_step(text, keys, after):
    engine = undoing_on(text)
    buffer = buffer_of(engine)

    feed(engine, keys)
    assert buffer.text == after
    assert len(buffer.undo_steps) == 1

    feed(engine, "u")
    assert buffer.text == text
    assert buffer.cursor == (0, 0)

    engine.feed("ctrl+r")
    assert buffer.text == after


def test_commands_undo_one_at_a_time_newest_first():
    engine = undoing_on("abc")
    buffer = buffer_of(engine)

    feed(engine, "xx")
    assert buffer.text == "c"

    feed(engine, "u")
    assert buffer.text == "bc"

    feed(engine, "u")
    assert buffer.text == "abc"


def test_a_whole_insert_session_is_one_step():
    engine = undoing_on("abc", (0, 1))
    buffer = buffer_of(engine)

    feed(engine, "i")
    typing(engine, "hello")
    typing(engine, " there")
    engine.feed("escape")
    assert buffer.text == "ahello therebc"

    feed(engine, "u")
    assert buffer.text == "abc"
    assert buffer.cursor == (0, 1)

    engine.feed("ctrl+r")
    assert buffer.text == "ahello therebc"


@pytest.mark.parametrize("keys", ["cw", "cc", "C", "o", "O", "A"])
def test_a_command_that_enters_insert_is_one_step_with_its_session(keys):
    text = "one two\nthree"
    engine = undoing_on(text)
    buffer = buffer_of(engine)

    feed(engine, keys)
    assert engine.mode == MODE_INSERT
    typing(engine, "new")
    engine.feed("escape")
    assert buffer.text != text
    assert len(buffer.undo_steps) == 1

    feed(engine, "u")
    assert buffer.text == text
    assert buffer.cursor == (0, 0)


def test_a_host_entering_insert_opens_one_step_until_it_leaves():
    engine = undoing_on("abc")
    buffer = buffer_of(engine)

    engine.set_mode(MODE_INSERT)
    typing(engine, "pasted")
    engine.set_mode(MODE_NORMAL)
    assert buffer.text == "pastedabc"

    feed(engine, "u")
    assert buffer.text == "abc"


def test_what_changes_nothing_takes_no_step():
    engine = undoing_on("abc\ndef")
    buffer = buffer_of(engine)

    feed(engine, "x")
    feed(engine, "l")
    feed(engine, "i")
    engine.feed("escape")
    feed(engine, "d")
    engine.feed("escape")
    assert len(buffer.undo_steps) == 1

    feed(engine, "u")
    assert buffer.text == "abc\ndef"
    assert buffer.undo_steps == []


def test_a_count_takes_that_many_steps():
    engine = undoing_on("abcde")
    buffer = buffer_of(engine)

    feed(engine, "xxx")
    feed(engine, "2u")
    assert buffer.text == "bcde"

    engine.feed("2")
    engine.feed("ctrl+r")
    assert buffer.text == "de"


def test_a_new_change_forgets_what_was_undone():
    engine = undoing_on("abc")
    buffer = buffer_of(engine)

    feed(engine, "xu")
    feed(engine, "ö")
    feed(engine, "x")
    assert buffer.text == "ac"

    engine.feed("ctrl+r")
    assert buffer.text == "ac"


def test_with_nothing_to_undo_or_redo_the_keys_still_do_nothing():
    engine = undoing_on("abc", (0, 1))
    buffer = buffer_of(engine)

    assert engine.feed("u") is True
    assert engine.feed("ctrl+r") is True
    assert buffer.text == "abc"
    assert buffer.cursor == (0, 1)


def test_undo_leaves_the_register_alone():
    engine = undoing_on("abc")

    feed(engine, "x")
    feed(engine, "u")
    assert engine.register == Register("a", linewise=False)


def test_the_cursor_after_a_redo_stands_on_a_character():
    engine = undoing_on("abc", (0, 2))
    buffer = buffer_of(engine)

    feed(engine, "xu")
    assert buffer.cursor == (0, 2)

    engine.feed("ctrl+r")
    assert buffer.text == "ab"
    assert buffer.cursor == (0, 1)


def test_undo_means_nothing_after_an_operator():
    engine = undoing_on("abc")
    buffer = buffer_of(engine)

    feed(engine, "x")
    feed(engine, "du")
    assert buffer.text == "bc"
    assert engine.pending == ""


def test_undo_works_on_a_single_line_host():
    engine = undoing_on("abc", multiline=False)
    buffer = buffer_of(engine)

    feed(engine, "x")
    feed(engine, "u")
    assert buffer.text == "abc"


# ------------------------------------------------------------------
# ------------------------- Search ---------------------------------
# ------------------------------------------------------------------


def searched(
    text: str, query: str, cursor: Tuple[int, int] = (0, 0), **options
) -> VimEngine:
    """An engine on `text` with `query` searched for and confirmed."""

    engine = engine_on(text, cursor, **options)
    feed(engine, "?" + query)
    engine.feed("enter")
    return engine


def test_question_mark_opens_a_prompt_that_takes_every_character():
    engine = engine_on("nothing here")

    assert engine.search_prompt is None

    feed(engine, "?")
    assert engine.search_prompt == ""
    assert engine.mode == MODE_NORMAL

    # Keys that mean something in NORMAL are just text in here
    feed(engine, "dd i")
    assert engine.search_prompt == "dd i"
    assert buffer_of(engine).text == "nothing here"
    assert buffer_of(engine).cursor == (0, 0)


def test_the_cursor_follows_the_first_match_forward_while_typing():
    engine = engine_on("foo bar\nbaz bar\nfoo", (0, 0))

    engine.feed("?")
    engine.feed("b")
    assert buffer_of(engine).cursor == (0, 4)

    engine.feed("a")
    assert buffer_of(engine).cursor == (0, 4)

    engine.feed("z")
    assert buffer_of(engine).cursor == (1, 0)


def test_the_match_under_the_cursor_is_not_the_first_one():
    assert buffer_of(searched("foo foo", "foo")).cursor == (0, 4)


def test_while_typing_every_match_is_highlighted():
    engine = engine_on("foo bar\nbaz foo")
    feed(engine, "?foo")

    assert engine.search_matches == ((0, 0, 3), (1, 4, 7))


def test_backspace_narrows_back_and_an_empty_prompt_goes_back_to_the_start():
    engine = engine_on("ab\nac", (0, 1))

    feed(engine, "?ac")
    assert buffer_of(engine).cursor == (1, 0)

    engine.feed("backspace")
    assert engine.search_prompt == "a"
    assert buffer_of(engine).cursor == (1, 0)

    engine.feed("backspace")
    assert engine.search_prompt == ""
    assert buffer_of(engine).cursor == (0, 1)
    assert engine.search_matches == ()


def test_backspace_on_an_empty_prompt_closes_it():
    engine = engine_on("abc")
    feed(engine, "?")
    engine.feed("backspace")

    assert engine.search_prompt is None


def test_a_key_with_no_character_does_nothing_in_the_prompt():
    engine = engine_on("abc")
    feed(engine, "?a")

    assert engine.feed("tab") is True
    assert engine.feed("<ctrl+d>") is True
    assert engine.search_prompt == "a"


def test_no_match_while_typing_leaves_the_cursor_where_it_began():
    engine = engine_on("foo bar", (0, 2))
    feed(engine, "?bar")
    assert buffer_of(engine).cursor == (0, 4)

    engine.feed("x")
    assert buffer_of(engine).cursor == (0, 2)
    assert engine.search_matches == ()


def test_enter_confirms_and_keeps_the_cursor_on_the_match():
    engine = searched("foo bar", "bar")

    assert engine.search_prompt is None
    assert buffer_of(engine).cursor == (0, 4)
    assert engine.search_matches == ((0, 4, 7),)
    assert buffer_of(engine).reports == []


def test_enter_on_nothing_found_says_so():
    engine = searched("foo", "[nope]", (0, 1))

    assert buffer_of(engine).cursor == (0, 1)
    assert buffer_of(engine).reports == ["Not found: [nope]"]


def test_enter_on_an_empty_prompt_with_no_search_does_nothing():
    engine = searched("foo", "", (0, 1))

    assert engine.search_prompt is None
    assert buffer_of(engine).cursor == (0, 1)
    assert buffer_of(engine).reports == []


def test_enter_on_an_empty_prompt_searches_again():
    engine = searched("foo foo foo", "foo")
    feed(engine, "?")
    engine.feed("enter")

    assert buffer_of(engine).cursor == (0, 8)


def test_a_search_that_wraps_while_typing_says_so_when_confirmed():
    engine = engine_on("bar foo", (0, 5))
    feed(engine, "?bar")

    assert buffer_of(engine).cursor == (0, 0)
    assert buffer_of(engine).reports == []

    engine.feed("enter")
    assert buffer_of(engine).reports == ["Search wrapped to the top"]


def test_escape_cancels_the_prompt_restoring_the_cursor_and_what_was_lit():
    engine = searched("foo bar\nbaz", "foo")
    place = buffer_of(engine).cursor

    feed(engine, "?baz")
    assert buffer_of(engine).cursor == (1, 0)
    assert engine.search_matches == ((1, 0, 3),)

    assert engine.feed("escape") is True
    assert engine.search_prompt is None
    assert buffer_of(engine).cursor == place
    assert engine.search_matches == ((0, 0, 3),)

    # The cancelled search isn't remembered
    engine.feed("n")
    assert buffer_of(engine).cursor == (0, 0)


def test_the_prompt_tells_the_host_each_time_it_changes():
    engine = engine_on("foo")

    feed(engine, "?f")
    assert buffer_of(engine).prompts_shown == 2

    engine.feed("backspace")
    assert buffer_of(engine).prompts_shown == 3

    engine.feed("escape")
    assert buffer_of(engine).prompts_shown == 4


@pytest.mark.parametrize(
    "query, cursor",
    [
        ("foo", (0, 4)),
        ("FOO", (0, 8)),
        ("Foo", (0, 4)),
    ],
)
def test_case_is_ignored_unless_the_search_has_a_capital(query, cursor):
    assert buffer_of(searched("foo Foo FOO", query)).cursor == cursor


def test_search_is_plain_text_not_a_pattern():
    assert buffer_of(searched("abc a.c", "a.c")).cursor == (0, 4)
    assert buffer_of(searched("abc (x", "(x")).cursor == (0, 4)


def test_a_search_matches_the_raw_text():
    engine = searched("[name](http://url.example)", "url")

    assert buffer_of(engine).cursor == (0, 14)


def test_n_goes_forward_and_wraps_saying_so():
    engine = searched("foo x foo", "foo")
    assert buffer_of(engine).cursor == (0, 6)

    engine.feed("n")
    assert buffer_of(engine).cursor == (0, 0)
    assert buffer_of(engine).reports[-1] == "Search wrapped to the top"


def test_big_n_goes_backward_and_wraps_saying_so():
    engine = searched("foo x foo y", "foo")
    engine.feed("N")
    assert buffer_of(engine).cursor == (0, 0)
    assert buffer_of(engine).reports == []

    engine.feed("N")
    assert buffer_of(engine).cursor == (0, 6)
    assert buffer_of(engine).reports[-1] == "Search wrapped to the bottom"


def test_n_goes_across_lines_and_takes_a_count():
    engine = searched("a\nb a\n\na\na", "a", (4, 0))
    assert buffer_of(engine).cursor == (0, 0)

    feed(engine, "2n")
    assert buffer_of(engine).cursor == (3, 0)
    feed(engine, "2N")
    assert buffer_of(engine).cursor == (0, 0)


def test_matches_never_overlap():
    engine = searched("aaaaa", "aa")

    assert engine.search_matches == ((0, 0, 2), (0, 2, 4))
    assert buffer_of(engine).cursor == (0, 2)


def test_a_count_on_the_prompt_goes_that_many_matches_along():
    engine = engine_on("foo foo foo foo")
    feed(engine, "3?foo")
    assert buffer_of(engine).cursor == (0, 4)

    engine.feed("enter")
    assert buffer_of(engine).cursor == (0, 12)


def test_n_with_no_search_yet_says_so():
    engine = engine_on("foo")

    for key in "nN":
        buffer_of(engine).reports.clear()
        assert engine.feed(key) is True
        assert buffer_of(engine).reports == ["No search yet"]
        assert buffer_of(engine).cursor == (0, 0)


def test_n_with_nothing_left_to_find_says_so():
    engine = searched("foo", "foo")
    buffer_of(engine).reports.clear()

    feed(engine, "ö")
    engine.keys.set("x", VimCommand.DELETE_LINE)
    engine.feed("x")
    assert buffer_of(engine).text == ""

    engine.feed("n")
    assert buffer_of(engine).reports == ["Not found: foo"]


def test_a_lone_match_wraps_onto_itself():
    engine = searched("foo", "foo")

    assert buffer_of(engine).cursor == (0, 0)
    assert buffer_of(engine).reports == ["Search wrapped to the top"]


def test_star_searches_the_word_under_the_cursor_as_a_whole_word():
    engine = engine_on("foo foobar foo", (0, 1))
    engine.feed("*")

    assert buffer_of(engine).cursor == (0, 11)
    assert engine.search_matches == ((0, 0, 3), (0, 11, 14))
    assert engine.search_prompt is None


def test_star_ignores_case_even_with_a_capital():
    engine = engine_on("Foo foo", (0, 0))
    engine.feed("*")

    assert buffer_of(engine).cursor == (0, 4)


def test_star_counts_umlauts_and_underscores_as_the_word():
    engine = engine_on("für fü_r fürs für")
    engine.feed("*")

    assert buffer_of(engine).cursor == (0, 14)


def test_star_counts_a_combining_umlaut_as_the_word():
    engine = engine_on("fu fu\u0308r fu")
    engine.feed("*")

    assert buffer_of(engine).cursor == (0, 8)


def test_star_on_blanks_takes_the_next_word_on_the_line():
    engine = engine_on("  foo foo", (0, 0))
    engine.feed("*")

    assert buffer_of(engine).cursor == (0, 6)


def test_star_with_no_word_says_so():
    engine = engine_on("foo\n  ", (1, 0))
    engine.feed("*")

    assert buffer_of(engine).reports == ["No word under the cursor"]
    assert engine.search_matches == ()


def test_n_after_star_stays_a_whole_word_search():
    engine = engine_on("foo foobar foo")
    feed(engine, "*n")

    assert buffer_of(engine).cursor == (0, 0)


def test_star_takes_a_count():
    engine = engine_on("foo foo foo foo")
    feed(engine, "2*")

    assert buffer_of(engine).cursor == (0, 8)


def test_highlights_stay_until_the_next_search():
    engine = searched("foo bar", "foo")
    feed(engine, "ö")

    assert engine.search_matches == ((0, 0, 3),)

    feed(engine, "?bar")
    engine.feed("enter")
    assert engine.search_matches == ((0, 4, 7),)


def test_highlights_follow_the_text_as_it_changes():
    engine = searched("foo bar foo", "foo")
    buffer_of(engine).replace((0, 0), (0, 4), "")

    assert engine.search_matches == ((0, 4, 7),)


def test_escape_clears_highlights_without_leaving_it_to_the_host():
    engine = searched("foo", "foo")

    assert engine.feed("escape") is True
    assert engine.search_matches == ()

    # Now it's the host's, to close the window
    assert engine.feed("escape") is False


def test_escape_leaves_a_pending_command_before_the_highlights():
    engine = searched("foo", "foo")
    engine.keys.set("d", VimOperator.DELETE)
    feed(engine, "d")

    engine.feed("escape")
    assert engine.pending == ""
    assert engine.search_matches == ((0, 0, 3),)


def test_escape_leaves_insert_before_the_highlights():
    engine = searched("foo", "foo")
    feed(engine, "i")

    engine.feed("escape")
    assert engine.mode == MODE_NORMAL
    assert engine.search_matches == ((0, 0, 3),)

    engine.feed("escape")
    assert engine.search_matches == ()


def test_a_search_with_nothing_to_show_doesnt_hold_escape_back():
    engine = searched("foo", "nope")

    assert engine.feed("escape") is False


def test_after_escape_n_still_works_and_lights_the_matches_again():
    engine = searched("foo foo", "foo")
    engine.feed("escape")

    engine.feed("n")
    assert buffer_of(engine).cursor == (0, 0)
    assert engine.search_matches == ((0, 0, 3), (0, 4, 7))


def test_the_last_search_outlives_the_engine_through_its_memory():
    memory = SearchMemory()
    first = engine_on("foo foo", search_memory=memory)
    feed(first, "?foo")
    first.feed("enter")

    second = engine_on("x foo", search_memory=memory)
    assert second.search_matches == ()

    second.feed("n")
    assert buffer_of(second).cursor == (0, 2)
    assert memory.last == Search("foo")


def test_an_operator_takes_a_search_motion():
    engine = searched("foo bar foo", "foo")
    assert buffer_of(engine).cursor == (0, 8)

    engine.keys.set("d", VimOperator.DELETE)
    feed(engine, "gg")
    buffer_of(engine).cursor = (0, 0)
    feed(engine, "dn")

    assert buffer_of(engine).text == "foo"
    assert engine.register == Register("foo bar ", linewise=False)


def test_a_failed_search_motion_leaves_an_operator_with_nothing_to_take():
    engine = engine_on("foo")
    engine.keys.set("d", VimOperator.DELETE)
    feed(engine, "dn")

    assert buffer_of(engine).text == "foo"
    assert buffer_of(engine).reports == ["No search yet"]
    assert engine.pending == ""


def test_a_single_line_host_can_search_too():
    engine = searched("foo foo", "foo", multiline=False)

    assert buffer_of(engine).cursor == (0, 4)


# --- Search and replace ------------------------------------------------------


def replacing(
    text: str, query: str, cursor: Tuple[int, int] = (0, 0), **options
) -> VimEngine:
    """An engine on `text` with `query` searched for and `R` pressed."""

    engine = searched(text, query, cursor, **options)
    engine.keys.set("R", VimCommand.REPLACE_MATCHES)
    engine.keys.set("u", VimCommand.UNDO)
    engine.keys.set("d", VimOperator.DELETE)
    buffer_of(engine).reports.clear()
    feed(engine, "R")
    return engine


def replaced(text: str, query: str, replacement: str, **options) -> VimEngine:
    """`text` with every match of `query` replaced by `replacement`, confirmed."""

    engine = replacing(text, query, **options)
    feed(engine, replacement)
    engine.feed("enter")
    return engine


def test_r_opens_a_prompt_for_the_last_search_that_takes_every_character():
    engine = replacing("foo bar", "foo", (0, 4))

    assert engine.replace_prompt == ("foo", "")
    assert engine.mode == MODE_NORMAL

    # Keys that mean something in NORMAL are just text in here
    feed(engine, "dd uR")
    assert engine.replace_prompt == ("foo", "dd uR")
    assert buffer_of(engine).text == "foo bar"


def test_enter_replaces_every_match_and_says_how_many():
    engine = replaced("foo x foo\nfoo", "foo", "bar")
    buffer = buffer_of(engine)

    assert buffer.text == "bar x bar\nbar"
    assert buffer.reports == ["3 replaced"]
    assert engine.replace_prompt is None
    assert engine.mode == MODE_NORMAL


def test_the_cursor_stands_on_the_first_replacement():
    engine = replaced("x foo\nfoo", "foo", "bar", cursor=(1, 0))

    assert buffer_of(engine).cursor == (0, 2)


def test_an_empty_prompt_deletes_the_matches():
    engine = replaced("a, b, c,", ",", "")

    assert buffer_of(engine).text == "a b c"
    assert buffer_of(engine).reports == ["3 replaced"]
    # The first match's place is past the line's end now; it stays on the text
    assert buffer_of(engine).cursor == (0, 1)


def test_deleting_a_whole_line_of_matches_keeps_the_cursor_on_it():
    engine = replaced("ab\nfoo", "foo", "")

    assert buffer_of(engine).text == "ab\n"
    assert buffer_of(engine).cursor == (1, 0)


def test_escape_cancels_the_prompt_and_changes_nothing():
    engine = replacing("foo foo", "foo")
    before = buffer_of(engine).cursor
    feed(engine, "bar")

    assert engine.feed("escape") is True
    assert engine.replace_prompt is None
    assert buffer_of(engine).text == "foo foo"
    assert buffer_of(engine).cursor == before
    assert buffer_of(engine).undo_steps == []


def test_backspace_edits_the_prompt_and_on_an_empty_one_cancels_it():
    engine = replacing("foo", "foo")
    feed(engine, "ab")
    engine.feed("backspace")
    assert engine.replace_prompt == ("foo", "a")

    engine.feed("backspace")
    engine.feed("backspace")
    assert engine.replace_prompt is None
    assert buffer_of(engine).text == "foo"


def test_a_named_key_in_the_prompt_is_ignored():
    engine = replacing("foo", "foo")
    engine.feed("ctrl+d")

    assert engine.replace_prompt == ("foo", "")


@pytest.mark.parametrize(
    "query, result",
    [
        ("foo", "x x x"),
        ("Foo", "foo x FOO"),
    ],
)
def test_replace_ignores_case_unless_the_search_has_a_capital(query, result):
    assert buffer_of(replaced("foo Foo FOO", query, "x")).text == result


def test_replace_is_plain_text_not_a_pattern():
    assert buffer_of(replaced("abc a.c", "a.c", "Z")).text == "abc Z"
    assert buffer_of(replaced("a\\1 b", "\\1", "$0")).text == "a$0 b"


def test_replace_after_star_takes_whole_words_only():
    engine = engine_on("foo food foo", (0, 0))
    engine.keys.set("R", VimCommand.REPLACE_MATCHES)
    feed(engine, "*R")
    assert engine.replace_prompt == ("foo", "")

    feed(engine, "bar")
    engine.feed("enter")
    assert buffer_of(engine).text == "bar food bar"


def test_replace_works_on_the_raw_text():
    engine = replaced("[name](http://url.example)", "url", "site")

    assert buffer_of(engine).text == "[name](http://site.example)"


def test_a_replacement_holding_the_search_is_not_replaced_again():
    engine = replaced("a a", "a", "aa")

    assert buffer_of(engine).text == "aa aa"
    assert buffer_of(engine).reports == ["2 replaced"]


def test_one_replace_is_one_undo_step():
    engine = replaced("foo\nfoo\nfoo", "foo", "bar")
    assert len(buffer_of(engine).undo_steps) == 1

    engine.feed("u")
    assert buffer_of(engine).text == "foo\nfoo\nfoo"


def test_replace_leaves_the_register_alone():
    engine = replaced("foo bar", "foo", "")

    assert engine.register is None


def test_r_with_no_search_yet_says_so_and_opens_no_prompt():
    engine = engine_on("foo")
    engine.keys.set("R", VimCommand.REPLACE_MATCHES)
    feed(engine, "R")

    assert engine.replace_prompt is None
    assert buffer_of(engine).reports == ["No search yet"]


def test_with_no_match_it_says_so_opens_no_prompt_and_changes_nothing():
    engine = replacing("foo", "nope")

    assert engine.replace_prompt is None
    assert buffer_of(engine).reports == ["Not found: nope"]

    feed(engine, "x")
    assert buffer_of(engine).text == "foo"
    assert buffer_of(engine).undo_steps == []


def test_r_in_visual_leaves_it_and_replaces_the_whole_note():
    engine = searched("foo x foo", "foo")
    engine.keys.set("v", VimCommand.VISUAL)
    engine.keys.set("R", VimCommand.REPLACE_MATCHES)
    feed(engine, "vR")

    assert engine.mode == MODE_NORMAL
    assert engine.replace_prompt == ("foo", "")

    feed(engine, "y")
    engine.feed("enter")
    assert buffer_of(engine).text == "y x y"


def test_a_single_line_host_can_replace_too():
    engine = replaced("foo foo", "foo", "x", multiline=False)

    assert buffer_of(engine).text == "x x"


def test_r_uses_the_last_search_from_another_engine():
    memory = SearchMemory()
    first = engine_on("foo", search_memory=memory)
    feed(first, "?foo")
    first.feed("enter")

    second = engine_on("x foo", search_memory=memory)
    second.keys.set("R", VimCommand.REPLACE_MATCHES)
    feed(second, "Rbar")
    second.feed("enter")

    assert buffer_of(second).text == "x bar"


# --- Yank and paste -----------------------------------------------------------


def yank_keys() -> VimKeymap:
    keys = change_keys()
    keys.set("y", VimOperator.YANK)
    keys.set("yy", VimCommand.YANK_LINE)
    keys.set("p", VimCommand.PASTE_AFTER)
    keys.set("P", VimCommand.PASTE_BEFORE)
    keys.set("u", VimCommand.UNDO)
    return keys


def yanking_on(
    text: str, cursor: Tuple[int, int] = (0, 0), **options
) -> VimEngine:
    return VimEngine(MemoryBuffer(text, cursor), yank_keys(), **options)


@pytest.mark.parametrize(
    "text, start, keys, register, cursor",
    [
        ("ab cd", (0, 0), "yw", "ab ", (0, 0)),
        ("ab cd", (0, 3), "yb", "ab ", (0, 0)),
        ("ab cd", (0, 0), "ye", "ab", (0, 0)),
        ("ab cd", (0, 3), "y_", "cd", (0, 3)),
        ("ab cd", (0, 0), "yt ", "ab", (0, 0)),
        ("ab cd", (0, 0), "yf ", "ab ", (0, 0)),
        ("ab cd ef", (0, 0), "2yw", "ab cd ", (0, 0)),
        ("a b c d e f g", (0, 0), "2y3w", "a b c d e f ", (0, 0)),
    ],
)
def test_y_takes_any_motion_and_changes_no_text(text, start, keys, register, cursor):
    engine = yanking_on(text, start)

    feed(engine, keys)

    assert buffer_of(engine).text == text
    assert buffer_of(engine).cursor == cursor
    assert engine.mode == MODE_NORMAL
    assert engine.register == Register(register, linewise=False)
    assert engine.pending == ""


@pytest.mark.parametrize(
    "start, keys, register, cursor",
    [
        ((1, 1), "yy", "bb", (1, 1)),
        ((0, 1), "2yy", "aa\nbb", (0, 1)),
        ((1, 0), "9yy", "bb\ncc", (1, 0)),
        ((1, 1), "yk", "aa\nbb", (0, 1)),
        ((1, 1), "yl", "bb\ncc", (1, 1)),
        ((1, 1), "ygg", "aa\nbb", (0, 1)),
        ((0, 0), "yG", "aa\nbb\ncc", (0, 0)),
    ],
)
def test_whole_lines_are_yanked_as_lines(start, keys, register, cursor):
    engine = yanking_on("aa\nbb\ncc", start)

    feed(engine, keys)

    assert buffer_of(engine).text == "aa\nbb\ncc"
    assert buffer_of(engine).cursor == cursor
    assert engine.register == Register(register, linewise=True)


def test_a_yank_whose_motion_fails_takes_nothing():
    engine = yanking_on("abc")
    buffer_of(engine).clipboard = "kept"

    feed(engine, "yfz")
    feed(engine, "yk")

    assert engine.register is None
    assert buffer_of(engine).clipboard == "kept"


def test_yanking_is_no_undo_step():
    engine = yanking_on("abc")

    feed(engine, "yy")
    feed(engine, "yw")


# ------------------------------------------------------------------
# ------------------------- vim_flash ------------------------------
# ------------------------------------------------------------------


def flash_on(text: str, cursor: Tuple[int, int] = (0, 0), **options) -> VimEngine:
    engine = engine_on(text, cursor, **options)
    engine.keys.set("s", VimMotion.VIM_FLASH)
    engine.keys.set("d", VimOperator.DELETE)
    return engine


def flash_view(engine: VimEngine) -> VimFlashView:
    view = engine.vim_flash_view
    assert view is not None
    return view


def labels_of(engine: VimEngine) -> Dict[Tuple[int, int], Optional[str]]:
    return {(m.row, m.start): m.label for m in flash_view(engine).matches}


def test_s_opens_vim_flash_with_nothing_found_yet():
    engine = flash_on("foo bar")
    feed(engine, "s")

    assert engine.mode == MODE_FLASH
    assert labels_of(engine) == {}
    assert buffer_of(engine).modes == [MODE_FLASH]


def test_each_character_typed_narrows_the_matches():
    engine = flash_on("cat car dog")

    feed(engine, "sc")
    assert list(labels_of(engine)) == [(0, 0), (0, 4)]

    feed(engine, "at")
    assert list(labels_of(engine)) == [(0, 0)]
    assert flash_view(engine).text == "cat"


def test_vim_flash_never_moves_the_cursor_or_edits_while_typing():
    engine = flash_on("cat car", (0, 2))
    feed(engine, "sca")

    assert buffer_of(engine).cursor == (0, 2)
    assert buffer_of(engine).text == "cat car"
    assert engine.register is None


def test_matching_is_exact_not_fuzzy():
    engine = flash_on("c-a-t cat")
    feed(engine, "sca")

    assert list(labels_of(engine)) == [(0, 6)]


def test_lowercase_ignores_case_and_a_capital_makes_it_count():
    engine = flash_on("Foo foo")

    feed(engine, "sf")
    assert list(labels_of(engine)) == [(0, 0), (0, 4)]

    engine = flash_on("Foo foo")
    feed(engine, "sF")
    assert list(labels_of(engine)) == [(0, 0)]


def test_matches_can_overlap():
    engine = flash_on("aaa", vim_flash_alphabet="xy")
    feed(engine, "saa")

    assert list(labels_of(engine)) == [(0, 0), (0, 1)]


def test_the_closest_match_gets_the_first_label_in_either_direction():
    # After `x` come a, b and c, which leaves s, d, f for the labels
    engine = flash_on("xa xb xc", (0, 3))
    feed(engine, "sx")

    assert labels_of(engine) == {(0, 3): "s", (0, 0): "d", (0, 6): "f"}


def test_a_nearer_row_beats_a_nearer_column():
    engine = flash_on("xx\n\n\nyy xx\nxx", (3, 0), vim_flash_alphabet="abc")
    feed(engine, "sx")

    # Two rows of distance come after one, whatever the columns
    labels = labels_of(engine)
    assert labels[(3, 3)] == "a"
    assert labels[(3, 4)] == "b"
    assert labels[(4, 0)] == "c"
    assert labels[(4, 1)] == "A"

    # Above the cursor, the end of a row is what's nearer
    assert labels[(0, 1)] == "B"
    assert labels[(0, 0)] == "C"


def test_uppercase_labels_come_after_the_lowercase_ones():
    engine = flash_on("x1 x2 x3 x4", vim_flash_alphabet="ab")
    feed(engine, "sx")

    assert list(labels_of(engine).values()) == ["a", "b", "A", "B"]


def test_matches_beyond_the_labels_go_without():
    engine = flash_on("x1 x2 x3 x4 x5 x6", vim_flash_alphabet="ab")
    feed(engine, "sx")

    assert list(labels_of(engine).values()) == ["a", "b", "A", "B", None, None]


def test_a_label_never_continues_the_search_text():
    # `a` and `D` follow a match, so neither case of either can be a label
    engine = flash_on("xa xD xc", vim_flash_alphabet="abcd")
    feed(engine, "sx")

    assert labels_of(engine) == {(0, 0): "b", (0, 3): "B", (0, 6): None}


def test_a_character_that_continues_the_text_is_never_taken_for_a_label():
    engine = flash_on("xa xb", vim_flash_alphabet="abcd")
    feed(engine, "sxa")

    assert engine.mode == MODE_FLASH
    assert list(labels_of(engine)) == [(0, 0)]


def test_a_match_keeps_its_lowercase_label_as_the_text_narrows():
    engine = flash_on("abx aby", (0, 4), vim_flash_alphabet="pq")
    feed(engine, "sa")
    before = labels_of(engine)
    feed(engine, "b")

    assert before == {(0, 4): "p", (0, 0): "q"}
    assert labels_of(engine) == before


def test_pressing_a_label_jumps_there_and_ends_it():
    engine = flash_on("xa xb xc", (0, 3))
    feed(engine, "sxf")

    assert buffer_of(engine).cursor == (0, 6)
    assert engine.mode == MODE_NORMAL
    assert engine.vim_flash_view is None


def test_enter_jumps_to_the_next_match_after_the_cursor():
    engine = flash_on("xa xb xc", (0, 3))
    feed(engine, "sx")
    engine.feed("enter")

    assert buffer_of(engine).cursor == (0, 6)
    assert engine.mode == MODE_NORMAL


def test_enter_past_the_last_match_goes_round_to_the_first():
    engine = flash_on("xa xb xc", (0, 6))
    feed(engine, "sx")
    engine.feed("enter")

    assert buffer_of(engine).cursor == (0, 0)


def test_enter_goes_backwards_when_the_way_round_is_off_screen():
    engine = flash_on("xa\n\nxb\nyy\nzz", (3, 0))
    buffer_of(engine).visible_rows = range(1, 5)
    feed(engine, "sx")
    engine.feed("enter")

    # Forwards it would wrap to row 0, which isn't on screen
    assert buffer_of(engine).cursor == (2, 0)


def test_enter_with_nothing_typed_just_ends_it():
    engine = flash_on("xa", (0, 1))
    feed(engine, "s")
    engine.feed("enter")

    assert buffer_of(engine).cursor == (0, 1)
    assert engine.mode == MODE_NORMAL


def test_a_single_match_doesnt_jump_by_itself():
    engine = flash_on("xa yb", (0, 1))
    feed(engine, "sy")

    assert buffer_of(engine).cursor == (0, 1)
    assert engine.mode == MODE_FLASH
    assert labels_of(engine) == {(0, 3): "a"}


def test_escape_cancels_and_is_not_left_for_the_host_to_close_with():
    engine = flash_on("xa xb", (0, 1))
    feed(engine, "sx")

    assert engine.feed("escape") is True
    assert buffer_of(engine).cursor == (0, 1)
    assert engine.mode == MODE_NORMAL
    assert engine.vim_flash_view is None

    assert engine.feed("escape") is False


def test_escape_leaves_the_lit_search_for_the_next_escape():
    engine = flash_on("foo xa")
    feed(engine, "*")
    lit = engine.lit_search
    feed(engine, "sx")

    assert engine.feed("escape") is True
    assert engine.lit_search == lit
    assert engine.feed("escape") is True
    assert engine.lit_search is None


def test_typing_what_isnt_there_ends_it_where_it_was():
    engine = flash_on("xa xb", (0, 1))
    feed(engine, "sxq")

    assert buffer_of(engine).cursor == (0, 1)
    assert engine.mode == MODE_NORMAL


def test_backspace_takes_a_character_back_and_stays_when_empty():
    engine = flash_on("xa xb")
    feed(engine, "sxa")

    engine.feed("backspace")
    assert list(labels_of(engine)) == [(0, 0), (0, 3)]

    engine.feed("backspace")
    engine.feed("backspace")
    assert engine.mode == MODE_FLASH
    assert labels_of(engine) == {}


def test_a_key_with_a_name_means_nothing_in_vim_flash():
    engine = flash_on("xa xb")
    feed(engine, "sx")

    assert engine.feed("left") is True
    assert engine.mode == MODE_FLASH
    assert flash_view(engine).text == "x"


def test_only_the_rows_on_screen_are_searched():
    engine = flash_on("xa\nxb\nxc")
    buffer_of(engine).visible_rows = range(1, 2)
    feed(engine, "sx")

    assert list(labels_of(engine)) == [(1, 0)]


def test_a_link_matches_by_the_name_drawn_and_lands_on_that_name():
    text = "go [home](http://site) now"
    engine = flash_on(f"top\n{text}")
    buffer = buffer_of(engine)

    # Drawn as `go home now`: its columns, and the stored one behind each
    buffer.drawn[1] = (
        "go home now",
        [0, 1, 2, 4, 5, 6, 7, 22, 23, 24, 25, 26],
    )

    feed(engine, "sh")
    assert list(labels_of(engine)) == [(1, 4)]

    # The address has an `h` in it too, but that isn't drawn
    view = flash_view(engine)
    assert view.matches[0].end == 5
    assert view.matches[0].label == "a"

    feed(engine, "a")
    assert buffer.cursor == (1, 4)


def test_a_match_can_end_at_the_end_of_a_drawn_line_and_cross_hidden_markup():
    engine = flash_on("*bo*ld")
    buffer_of(engine).drawn[0] = ("bold", [1, 2, 4, 5, 6])

    feed(engine, "sbol")

    match = flash_view(engine).matches[0]
    assert (match.start, match.end) == (1, 5)


def test_a_click_elsewhere_ends_it():
    engine = flash_on("xa xb")
    feed(engine, "sx")

    buffer_of(engine).cursor = (0, 1)

    assert engine.vim_flash_view is None
    assert engine.mode == MODE_NORMAL


def test_vim_flash_makes_no_undo_step():
    engine = flash_on("xa xb")
    feed(engine, "sxs")

    assert buffer_of(engine).undo_steps == []


@pytest.mark.parametrize(
    "text, start, yank, paste, after, cursor",
    [
        # Characters: after or before the cursor, ending on the last one put
        ("ab cd", (0, 0), "ye", "p", "aabb cd", (0, 2)),
        ("ab cd", (0, 3), "yw", "P", "ab cdcd", (0, 4)),
        ("ab cd", (0, 0), "ye", "2p", "aababb cd", (0, 4)),
        # Lines: under or over the line, on its first non-blank
        ("ab\ncd", (0, 1), "yy", "p", "ab\nab\ncd", (1, 0)),
        ("ab\ncd", (1, 1), "yy", "p", "ab\ncd\ncd", (2, 0)),
        ("ab\ncd", (1, 1), "yy", "P", "ab\ncd\ncd", (1, 0)),
        ("ab\ncd", (0, 0), "yy", "2p", "ab\nab\nab\ncd", (1, 0)),
        ("  ab", (0, 3), "yy", "p", "  ab\n  ab", (1, 2)),
        ("ab\ncd", (0, 0), "2yy", "p", "ab\nab\ncd\ncd", (1, 0)),
    ],
)
def test_paste_respects_how_it_was_yanked(text, start, yank, paste, after, cursor):
    engine = yanking_on(text, start)
    feed(engine, yank)
    feed(engine, paste)

    assert buffer_of(engine).text == after
    assert buffer_of(engine).cursor == cursor
    assert engine.mode == MODE_NORMAL


def test_a_yank_over_lines_from_mid_line_pastes_as_characters_from_its_start():
    engine = yanking_on("ab\ncd\nef", (0, 1))
    feed(engine, "yfd")

    assert engine.register == Register("b\ncd", linewise=False)

    buffer_of(engine).move_cursor(2, 0)
    feed(engine, "p")

    assert buffer_of(engine).text == "ab\ncd\neb\ncdf"
    assert buffer_of(engine).cursor == (2, 1)


def test_paste_on_an_empty_line():
    engine = yanking_on("ab\n", (0, 0))
    feed(engine, "ye")
    buffer_of(engine).move_cursor(1, 0)

    feed(engine, "p")

    assert buffer_of(engine).text == "ab\nab"
    assert buffer_of(engine).cursor == (1, 1)


def test_a_paste_is_one_undo_step():
    engine = yanking_on("ab\ncd")
    feed(engine, "yy")
    feed(engine, "p")
    feed(engine, "u")

    assert buffer_of(engine).text == "ab\ncd"
    assert buffer_of(engine).cursor == (0, 0)


def test_with_nothing_to_paste_it_says_so():
    engine = yanking_on("ab")

    feed(engine, "p")

    assert buffer_of(engine).text == "ab"
    assert buffer_of(engine).reports == ["Nothing to paste"]


@pytest.mark.parametrize(
    "start, keys, paste, after",
    [
        ((0, 0), "dd", "p", "cd\nab"),
        ((0, 0), "dw", "P", "ab\ncd"),
        ((0, 0), "x", "p", "ba\ncd"),
        ((1, 0), "D", "P", "ab\ncd"),
    ],
)
def test_the_deletes_fill_the_register_for_paste(start, keys, paste, after):
    engine = yanking_on("ab\ncd", start)

    feed(engine, keys)
    feed(engine, paste)

    assert buffer_of(engine).text == after


def test_a_change_fills_the_register_too():
    engine = yanking_on("foo bar")

    feed(engine, "cw")
    engine.feed("escape")
    feed(engine, "P")

    assert engine.register == Register("foo", linewise=False)
    assert buffer_of(engine).text == "foo bar"


def test_the_register_outlives_the_engine():
    memory = RegisterMemory()
    first = VimEngine(MemoryBuffer("hello"), yank_keys(), register_memory=memory)
    feed(first, "yy")

    second = VimEngine(MemoryBuffer("other"), yank_keys(), register_memory=memory)
    buffer_of(second).clipboard = "hello"
    feed(second, "p")

    assert buffer_of(second).text == "other\nhello"
    assert second.register == Register("hello", linewise=True)


def test_y_copies_to_the_clipboard():
    engine = yanking_on("ab\ncd")

    feed(engine, "yw")
    assert buffer_of(engine).clipboard == "ab"

    feed(engine, "2yy")
    assert buffer_of(engine).clipboard == "ab\ncd"



def test_paste_uses_the_register_while_the_clipboard_holds_the_last_yank():
    engine = yanking_on("ab\ncd")
    feed(engine, "yy")

    # A delete takes the register, not the clipboard, and that's what's put
    buffer_of(engine).move_cursor(1, 0)
    feed(engine, "dd")
    feed(engine, "P")

    assert buffer_of(engine).text == "cd\nab"
    assert buffer_of(engine).clipboard_pastes == []


@pytest.mark.parametrize(
    "start, key, after, cursor",
    [
        ((0, 0), "p", "aXYb", (0, 2)),
        ((0, 1), "p", "abXY", (0, 3)),
        ((0, 0), "P", "XYab", (0, 1)),
    ],
)
def test_a_changed_clipboard_goes_through_the_hosts_paste(start, key, after, cursor):
    engine = yanking_on("ab", start)
    feed(engine, "yy")
    buffer_of(engine).clipboard = "XY"

    feed(engine, key)

    assert buffer_of(engine).clipboard_pastes == ["XY"]
    assert buffer_of(engine).text == after
    assert buffer_of(engine).cursor == cursor
    assert engine.mode == MODE_NORMAL


def test_a_multiline_clipboard_leaves_the_cursor_where_it_began():
    engine = yanking_on("ab")
    buffer_of(engine).clipboard = "X\nY"

    feed(engine, "p")

    assert buffer_of(engine).text == "aX\nYb"
    assert buffer_of(engine).cursor == (0, 1)


def test_a_clipboard_paste_is_one_undo_step_and_counts():
    engine = yanking_on("ab")
    buffer_of(engine).clipboard = "X"

    feed(engine, "2p")
    assert buffer_of(engine).text == "aXXb"
    assert engine.mode == MODE_NORMAL

    feed(engine, "u")
    assert buffer_of(engine).text == "ab"


def test_a_clipboard_paste_leaves_gi_where_it_was():
    engine = yanking_on("ab cd", (0, 0))
    feed(engine, "i")
    engine.feed("escape")
    buffer_of(engine).clipboard = "X"
    buffer_of(engine).move_cursor(0, 3)
    feed(engine, "p")

    keys = engine.keys
    keys.set("gi", VimCommand.INSERT_AT_LAST)
    feed(engine, "gi")

    assert buffer_of(engine).cursor == (0, 0)


def test_what_came_off_the_clipboard_is_in_the_register_from_then_on():
    engine = yanking_on("ab\ncd")
    buffer_of(engine).clipboard = "X"

    feed(engine, "p")
    assert engine.register == Register("X", linewise=False, from_clipboard=True)

    # Move a line: the clipboard was taken up, so it doesn't get in the way
    feed(engine, "dd")
    feed(engine, "p")

    assert buffer_of(engine).text == "cd\naXb"
    assert buffer_of(engine).clipboard_pastes == ["X"]


def test_clipboard_text_pastes_the_same_way_every_time():
    engine = yanking_on("ab")
    buffer_of(engine).clipboard = "X"

    feed(engine, "p")
    feed(engine, "p")

    assert buffer_of(engine).clipboard_pastes == ["X", "X"]
    assert buffer_of(engine).text == "aXXb"


def test_an_empty_clipboard_is_no_news():
    engine = yanking_on("ab\ncd")
    feed(engine, "yy")
    buffer_of(engine).clipboard = ""

    feed(engine, "p")

    assert buffer_of(engine).text == "ab\nab\ncd"
    assert buffer_of(engine).clipboard_pastes == []


def test_a_clipboard_that_only_came_back_reformatted_is_no_news():
    """Some hosts hand back CRLF, or take a trailing line break off or put one on."""

    engine = yanking_on("ab\ncd")
    feed(engine, "2yy")
    buffer_of(engine).clipboard = "ab\r\ncd\r\n"

    feed(engine, "p")

    assert buffer_of(engine).clipboard_pastes == []


def test_a_clipboard_with_no_yank_yet_is_pasted():
    engine = yanking_on("ab")
    buffer_of(engine).clipboard = "from before"

    feed(engine, "P")

    assert buffer_of(engine).text == "from beforeab"


def on_a_clipboard_already_holding(clipboard: str, text: str) -> VimEngine:
    buffer = MemoryBuffer(text)
    buffer.clipboard = clipboard
    return VimEngine(buffer, yank_keys())


def test_a_clipboard_older_than_the_engine_is_pasted_with_nothing_else_to_paste():
    engine = on_a_clipboard_already_holding("from before", "ab")

    feed(engine, "P")

    assert buffer_of(engine).text == "from beforeab"


def test_a_clipboard_older_than_the_engine_doesnt_stop_dd_p():
    engine = on_a_clipboard_already_holding("from before", "ab\ncd")

    feed(engine, "dd")
    feed(engine, "p")

    assert buffer_of(engine).text == "cd\nab"
    assert buffer_of(engine).clipboard_pastes == []


def test_a_clipboard_changed_before_the_first_delete_still_wins_over_it():
    engine = yanking_on("abc")
    buffer_of(engine).clipboard = "X"

    feed(engine, "x")
    feed(engine, "p")

    assert buffer_of(engine).clipboard_pastes == ["X"]


def test_a_delete_never_reads_the_clipboard():
    engine = yanking_on("a\nb\nc")
    reads = buffer_of(engine).clipboard_reads

    feed(engine, "dd")
    feed(engine, "dd")

    assert buffer_of(engine).clipboard_reads == reads


def test_a_clipboard_changed_after_a_delete_wins_over_it():
    engine = yanking_on("ab\ncd")

    feed(engine, "dd")
    buffer_of(engine).clipboard = "X"
    feed(engine, "P")

    assert buffer_of(engine).text == "Xcd"


def test_yy_is_left_to_a_single_line_host():
    engine = yanking_on("ab", multiline=False)

    assert engine.feed("y")
    assert engine.feed("y") is True
    assert engine.register is None
    assert engine.pending == ""


def nesting_keys() -> VimKeymap:
    keys = change_keys()
    keys.set(">", VimOperator.INDENT)
    keys.set("<", VimOperator.UNINDENT)
    keys.set(">>", VimCommand.INDENT_LINE)
    keys.set("<<", VimCommand.UNINDENT_LINE)
    return keys


def nesting_on(text: str, cursor: Tuple[int, int] = (0, 0), **options) -> VimEngine:
    return VimEngine(MemoryBuffer(text, cursor), nesting_keys(), **options)


@pytest.mark.parametrize(
    "text, start, keys, after, cursor",
    [
        # One level, and the cursor on the line's first non-blank, as in vim
        ("foo", (0, 2), ">>", "  foo", (0, 2)),
        ("  foo", (0, 4), "<<", "foo", (0, 0)),
        ("  foo", (0, 0), ">>", "    foo", (0, 4)),
        ("- foo", (0, 3), ">>", "  - foo", (0, 2)),
        ("  - foo", (0, 5), "<<", "- foo", (0, 0)),
        # Nothing left to take out
        ("foo", (0, 2), "<<", "foo", (0, 0)),
        # An indent off the levels lands on one, as `tab` lands it
        ("   foo", (0, 0), ">>", "    foo", (0, 4)),
        ("   foo", (0, 0), "<<", "foo", (0, 0)),
        ("\tfoo", (0, 0), ">>", "    foo", (0, 4)),
        # A quoted line nests after its bar
        ("> foo", (0, 3), ">>", ">   foo", (0, 0)),
        (">   foo", (0, 5), "<<", "> foo", (0, 0)),
        ("> foo", (0, 3), "<<", "> foo", (0, 0)),
        (">   - foo", (0, 0), "<<", "> - foo", (0, 0)),
        # There's nothing to nest on an empty line, as in vim
        ("", (0, 0), ">>", "", (0, 0)),
        ("> ", (0, 0), ">>", "> ", (0, 0)),
    ],
)
def test_doubling_the_operator_nests_the_line(text, start, keys, after, cursor):
    engine = nesting_on(text, start)

    feed(engine, keys)

    assert buffer_of(engine).text == after
    assert buffer_of(engine).cursor == cursor


# As in flash.nvim, the jump after an operator takes the target's character too
def test_ds_deletes_forward_up_to_and_with_the_target():
    engine = flash_on("xa xb xc")
    feed(engine, "dsxb")
    assert engine.mode == MODE_FLASH

    feed(engine, labels_of(engine)[(0, 3)] or "")

    assert buffer_of(engine).text == "b xc"
    assert buffer_of(engine).cursor == (0, 0)
    assert engine.register == Register("xa x", linewise=False)
    assert engine.mode == MODE_NORMAL
    assert engine.pending == ""


def test_ds_deletes_backward_with_the_cursors_own_character():
    engine = flash_on("xa xb xc", (0, 6))
    feed(engine, "dsxa")
    feed(engine, labels_of(engine)[(0, 0)] or "")

    assert buffer_of(engine).text == "c"
    assert engine.register == Register("xa xb x", linewise=False)


def test_ds_across_lines_takes_characters_not_lines():
    engine = flash_on("ab\ncd\nef", (0, 1))
    feed(engine, "dse")
    feed(engine, labels_of(engine)[(2, 0)] or "")

    assert buffer_of(engine).text == "af"
    assert engine.register == Register("b\ncd\ne", linewise=False)


def test_ds_with_enter_takes_up_to_the_next_match():
    engine = flash_on("xa xb xc", (0, 1))
    feed(engine, "dsx")
    engine.feed("enter")

    assert buffer_of(engine).text == "xb xc"


def test_cs_changes_up_to_the_target_and_inserts_there():
    engine = flash_on("xa xb xc")
    engine.keys.set("c", VimOperator.CHANGE)
    feed(engine, "csxb")
    feed(engine, labels_of(engine)[(0, 3)] or "")

    assert buffer_of(engine).text == "b xc"
    assert buffer_of(engine).cursor == (0, 0)
    assert engine.mode == MODE_INSERT


def test_escape_in_vim_flash_cancels_the_operator_too():
    engine = flash_on("xa xb")
    feed(engine, "dsx")
    engine.feed("escape")

    assert engine.mode == MODE_NORMAL
    assert engine.pending == ""
    assert buffer_of(engine).text == "xa xb"

    feed(engine, "x")
    assert buffer_of(engine).text == "xa xb"


def test_nothing_left_to_go_to_leaves_the_operator_with_nothing_to_take():
    engine = flash_on("xa xb", (0, 1))
    feed(engine, "dsxq")

    assert buffer_of(engine).text == "xa xb"
    assert engine.mode == MODE_NORMAL
    assert engine.pending == ""


@pytest.mark.parametrize(
    "start, keys, after, cursor",
    [
        ((0, 1), "2>>", "  a\n  b\nc", (0, 2)),
        ((1, 0), "5>>", "a\n  b\n  c", (1, 2)),
        ((0, 0), "3>>", "  a\n  b\n  c", (0, 2)),
    ],
)
def test_a_count_nests_that_many_lines_one_level(start, keys, after, cursor):
    engine = nesting_on("a\nb\nc", start)

    feed(engine, keys)

    assert buffer_of(engine).text == after
    assert buffer_of(engine).cursor == cursor


def test_a_count_unnests_too_and_passes_over_empty_lines():
    engine = nesting_on("  a\n\n  b")

    feed(engine, "3<<")

    assert buffer_of(engine).text == "a\n\nb"


def test_nesting_leaves_the_register_alone():
    engine = nesting_on("foo bar\nbaz")
    feed(engine, "dw")
    register = engine.register

    feed(engine, ">>")
    feed(engine, "<<")

    assert engine.register == register


def test_nesting_lines_is_one_undo_step():
    engine = nesting_on("a\nb\nc", (0, 0))

    feed(engine, "3>>")
    assert len(buffer_of(engine).undo_steps) == 1

    buffer_of(engine).undo()
    assert buffer_of(engine).text == "a\nb\nc"


def test_a_single_line_host_has_no_nesting():
    engine = nesting_on("abc", multiline=False)

    feed(engine, ">>")
    feed(engine, "<<")

    assert buffer_of(engine).text == "abc"
    assert engine.pending == ""


@pytest.mark.parametrize(
    "text, start, keys, after, cursor",
    [
        # Whole lines, whichever way the motion goes
        ("a\nb\nc", (0, 0), ">l", "  a\n  b\nc", (0, 2)),
        ("a\nb\nc", (2, 0), ">k", "a\n  b\n  c", (1, 2)),
        ("a\nb\nc", (0, 0), ">G", "  a\n  b\n  c", (0, 2)),
        ("a\nb\nc", (1, 0), ">gg", "  a\n  b\nc", (0, 2)),
        ("  a\n  b\nc", (0, 0), "<l", "a\nb\nc", (0, 0)),
        # A character motion takes the lines it touches, however little of them
        ("foo bar", (0, 4), ">w", "  foo bar", (0, 2)),
        ("foo bar", (0, 4), ">e", "  foo bar", (0, 2)),
        ("foo bar", (0, 6), ">ö", "  foo bar", (0, 2)),
        ("foo bar", (0, 4), ">_", "  foo bar", (0, 2)),
        ("foo bar", (0, 4), ">fr", "  foo bar", (0, 2)),
        ("  foo", (0, 3), "<=", "foo", (0, 0)),
        ("foo\nbar", (0, 2), ">e", "  foo\n  bar", (0, 2)),
        # `w` stops at the end of the line's last word, as `dw` does
        ("foo\nbar", (0, 2), ">w", "  foo\nbar", (0, 2)),
        # Stopping short of a line's start leaves that line out
        ("a\nb\n\nc", (0, 0), ">}", "  a\n  b\n\nc", (0, 2)),
        # Counts multiply
        ("a\nb\nc\nd", (0, 0), "2>l", "  a\n  b\n  c\nd", (0, 2)),
        # Blank lines in the way stay empty
        ("a\n\nb", (0, 0), ">G", "  a\n\n  b", (0, 2)),
        # A quote nests after its bar on every line
        ("> a\n> b", (0, 0), ">l", ">   a\n>   b", (0, 0)),
    ],
)
def test_the_nesting_operators_take_a_motion(text, start, keys, after, cursor):
    keys_bound = nesting_keys()
    keys_bound.set("G", VimMotion.BOTTOM)
    keys_bound.set("gg", VimMotion.TOP)
    keys_bound.set("}", VimMotion.PARAGRAPH_DOWN)
    engine = VimEngine(MemoryBuffer(text, start), keys_bound)

    feed(engine, keys)

    assert buffer_of(engine).text == after
    assert buffer_of(engine).cursor == cursor
    assert engine.register is None
    assert engine.mode == MODE_NORMAL
    assert engine.pending == ""


@pytest.mark.parametrize(
    "text, start, keys",
    [
        # A motion that fails has nothing to act on
        ("a\nb", (0, 0), ">k"),
        ("a\nb", (1, 0), ">l"),
        ("foo", (0, 0), ">j"),
        ("foo", (0, 0), ">fz"),
        # A key that's no motion cancels it
        ("foo", (0, 0), ">q"),
    ],
)
def test_a_nesting_operator_without_a_motion_does_nothing(text, start, keys):
    engine = nesting_on(text, start)

    feed(engine, keys)

    assert buffer_of(engine).text == text
    assert buffer_of(engine).cursor == start
    assert engine.pending == ""


def test_the_nesting_operators_can_move_to_other_keys():
    keys = nesting_keys()
    keys.remap({">": "+"})
    engine = VimEngine(MemoryBuffer("a\nb"), keys)

    feed(engine, "+l")

    assert buffer_of(engine).text == "  a\n  b"


def paragraph_keys() -> VimKeymap:
    keys = nesting_keys()
    keys.set("ip", VimTextObject.INNER_PARAGRAPH)
    keys.set("ap", VimTextObject.AROUND_PARAGRAPH)
    return keys


def paragraphs_on(text: str, cursor: Tuple[int, int] = (0, 0), **options) -> VimEngine:
    return VimEngine(MemoryBuffer(text, cursor), paragraph_keys(), **options)


@pytest.mark.parametrize(
    "text, start, keys, after, cursor",
    [
        # The paragraph around the cursor, from anywhere in it
        ("a\nb\n\nc", (0, 0), ">ip", "  a\n  b\n\nc", (0, 2)),
        ("a\nb\n\nc", (1, 0), ">ip", "  a\n  b\n\nc", (0, 2)),
        ("a\n\nb\nc", (3, 0), ">ip", "a\n\n  b\n  c", (2, 2)),
        ("  a\n  b\n\nc", (1, 0), "<ip", "a\nb\n\nc", (0, 0)),
        # `ap` takes the blanks after it, or if there are none, those before it
        ("a\n\nb", (0, 0), ">ap", "  a\n\nb", (0, 2)),
        ("a\n\nb", (2, 0), ">ap", "a\n\n  b", (1, 0)),
        # From a blank line, `ap` takes the paragraph after it
        ("a\n\nb\nc\n\nd", (1, 0), ">ap", "a\n\n  b\n  c\n\nd", (1, 0)),
        # A count takes the runs in turn: blanks count as one on their own
        ("a\n\nb\n\nc", (0, 0), ">3ip", "  a\n\n  b\n\nc", (0, 2)),
        ("a\n\nb\n\nc", (0, 0), ">2ap", "  a\n\n  b\n\nc", (0, 2)),
        ("a\n\nb", (0, 0), "9>ip", "  a\n\n  b", (0, 2)),
        # A line of nothing but blanks separates too
        ("a\n  \nb", (0, 0), ">ip", "  a\n  \nb", (0, 2)),
    ],
)
def test_the_nesting_operators_take_a_paragraph(text, start, keys, after, cursor):
    engine = paragraphs_on(text, start)

    feed(engine, keys)

    assert buffer_of(engine).text == after
    assert buffer_of(engine).cursor == cursor
    assert engine.register is None
    assert engine.mode == MODE_NORMAL
    assert engine.pending == ""


@pytest.mark.parametrize(
    "keys, after, register",
    [
        ("dip", "\nc", "a\nb"),
        ("dap", "c", "a\nb\n"),
    ],
)
def test_deleting_a_paragraph_takes_whole_lines(keys, after, register):
    engine = paragraphs_on("a\nb\n\nc")

    feed(engine, keys)

    assert buffer_of(engine).text == after
    assert engine.register == Register(register, linewise=True)


def test_changing_a_paragraph_leaves_one_line_to_type_on():
    engine = paragraphs_on("a\nb\n\nc")

    feed(engine, "cip")

    assert buffer_of(engine).text == "\n\nc"
    assert buffer_of(engine).cursor == (0, 0)
    assert engine.mode == MODE_INSERT


def test_a_text_object_binding_waits_only_behind_an_operator():
    engine = paragraphs_on("abc")

    engine.feed("i")
    assert engine.mode == MODE_INSERT
    assert engine.pending == ""


def test_a_text_object_alone_or_half_typed_does_nothing():
    engine = paragraphs_on("a\nb")

    feed(engine, ">i")
    assert engine.pending == ">i"

    feed(engine, "q")
    assert engine.pending == ""
    assert buffer_of(engine).text == "a\nb"


def test_a_single_line_host_has_no_paragraphs():
    engine = paragraphs_on("abc", multiline=False)

    feed(engine, "dip")

    assert buffer_of(engine).text == "abc"
    assert engine.pending == ""


def text_object_keys() -> VimKeymap:
    keys = paragraph_keys()
    keys.set("y", VimOperator.YANK)
    keys.set("iw", VimTextObject.INNER_WORD)
    keys.set("aw", VimTextObject.AROUND_WORD)
    keys.set(["iW", "i "], VimTextObject.INNER_BIG_WORD)
    keys.set("aW", VimTextObject.AROUND_BIG_WORD)
    keys.set(["i(", "i)"], VimTextObject.INNER_PARENS)
    keys.set(["a(", "a)"], VimTextObject.AROUND_PARENS)
    keys.set(["i[", "i]"], VimTextObject.INNER_BRACKETS)
    keys.set(["a[", "a]"], VimTextObject.AROUND_BRACKETS)
    keys.set(["i{", "i}"], VimTextObject.INNER_BRACES)
    keys.set(["a{", "a}"], VimTextObject.AROUND_BRACES)
    keys.set(["i<", "i>"], VimTextObject.INNER_ANGLES)
    keys.set(["a<", "a>"], VimTextObject.AROUND_ANGLES)
    keys.set('i"', VimTextObject.INNER_DOUBLE_QUOTES)
    keys.set('a"', VimTextObject.AROUND_DOUBLE_QUOTES)
    keys.set("i'", VimTextObject.INNER_SINGLE_QUOTES)
    keys.set("a'", VimTextObject.AROUND_SINGLE_QUOTES)
    keys.set("i`", VimTextObject.INNER_BACKTICKS)
    keys.set("a`", VimTextObject.AROUND_BACKTICKS)
    return keys


def objects_on(text: str, cursor: Tuple[int, int] = (0, 0), **options) -> VimEngine:
    return VimEngine(MemoryBuffer(text, cursor), text_object_keys(), **options)


@pytest.mark.parametrize(
    "text, start, keys, after, cursor, register",
    [
        # The word under the cursor, from anywhere in it
        ("foo bar baz", (0, 5), "diw", "foo  baz", (0, 4), "bar"),
        ("foo bar baz", (0, 4), "diw", "foo  baz", (0, 4), "bar"),
        # `aw` takes the blanks after it, as in vim
        ("foo bar baz", (0, 5), "daw", "foo baz", (0, 4), "bar "),
        # or with none after it, those before it
        ("foo bar", (0, 5), "daw", "foo", (0, 2), " bar"),
        # Punctuation is a word of its own, as for `w`
        ("foo.bar", (0, 4), "diw", "foo.", (0, 3), "bar"),
        ("foo.bar", (0, 3), "diw", "foobar", (0, 3), "."),
        # On blanks, `iw` takes them and `aw` takes the word after them too
        ("foo   bar", (0, 4), "diw", "foobar", (0, 3), "   "),
        ("foo   bar baz", (0, 4), "daw", "foo baz", (0, 3), "   bar"),
        # A count takes the runs in turn: blanks count as one on their own
        ("foo bar baz", (0, 0), "d3iw", " baz", (0, 0), "foo bar"),
        ("foo bar baz qux", (0, 0), "d2aw", "baz qux", (0, 0), "foo bar "),
        # Never past the line
        ("foo\nbar", (0, 1), "d5iw", "\nbar", (0, 0), "foo"),
        # Umlauts are letters
        ("für dich", (0, 1), "diw", " dich", (0, 0), "für"),
        # A WORD is anything but blanks
        ("foo a.b-c bar", (0, 6), "diW", "foo  bar", (0, 4), "a.b-c"),
        ("foo a.b-c bar", (0, 6), "daW", "foo bar", (0, 4), "a.b-c "),
        ("foo a.b-c bar", (0, 6), "di ", "foo  bar", (0, 4), "a.b-c"),
        ("foo a.b-c", (0, 6), "daW", "foo", (0, 2), " a.b-c"),
        # Only blanks count as the ones after it: punctuation stays
        ("(foo bar)", (0, 6), "daw", "(foo)", (0, 4), " bar"),
        ("foo bar.", (0, 5), "daw", "foo.", (0, 3), " bar"),
        ("foo, bar", (0, 1), "daw", ", bar", (0, 0), "foo"),
        # and a line's indent is never the blanks before it
        ("  foo", (0, 3), "daw", "  ", (0, 1), "foo"),
        ("x\n  foo", (1, 2), "daw", "x\n  ", (1, 1), "foo"),
        ("foo bar baz", (0, 5), "d2aW", "foo", (0, 2), " bar baz"),
    ],
)
def test_the_word_objects(text, start, keys, after, cursor, register):
    engine = objects_on(text, start)

    feed(engine, keys)

    assert buffer_of(engine).text == after
    assert buffer_of(engine).cursor == cursor
    assert engine.register == Register(register, linewise=False)
    assert engine.mode == MODE_NORMAL
    assert engine.pending == ""


def test_changing_a_word_leaves_insert_where_it_was():
    engine = objects_on("foo bar baz", (0, 5))

    feed(engine, "ciw")

    assert buffer_of(engine).text == "foo  baz"
    assert buffer_of(engine).cursor == (0, 4)
    assert engine.mode == MODE_INSERT
    assert engine.register == Register("bar", linewise=False)


def test_yanking_a_word_goes_to_its_start_and_changes_nothing():
    engine = objects_on("foo bar baz", (0, 6))

    feed(engine, "yiw")

    assert buffer_of(engine).text == "foo bar baz"
    assert buffer_of(engine).cursor == (0, 4)
    assert engine.register == Register("bar", linewise=False)
    assert buffer_of(engine).clipboard == "bar"


def test_an_empty_line_has_no_word_to_take():
    engine = objects_on("a\n\nb", (1, 0))

    feed(engine, "diw")

    assert buffer_of(engine).text == "a\n\nb"
    assert engine.register is None
    assert engine.pending == ""


@pytest.mark.parametrize(
    "text, start, keys, after, cursor, register",
    [
        # Inside the pair, and either of its keys
        ("f(a, b)", (0, 3), "di(", "f()", (0, 2), "a, b"),
        ("f(a, b)", (0, 3), "di)", "f()", (0, 2), "a, b"),
        ("x [a] y", (0, 3), "da[", "x  y", (0, 2), "[a]"),
        ("x {a} y", (0, 3), "di}", "x {} y", (0, 3), "a"),
        ("x <a> y", (0, 3), "da>", "x  y", (0, 2), "<a>"),
        # Standing on the pair itself
        ("f(a)", (0, 1), "di(", "f()", (0, 2), "a"),
        ("f(a)", (0, 3), "da(", "f", (0, 0), "(a)"),
        # The pair around the cursor, nested ones passed over; a count goes out
        ("(a (b) c)", (0, 1), "di(", "()", (0, 1), "a (b) c"),
        ("(a (b) c)", (0, 4), "di(", "(a () c)", (0, 4), "b"),
        ("(a (b) c)", (0, 4), "d2i(", "()", (0, 1), "a (b) c"),
        # Across lines
        ("f(a,\n  b)", (1, 2), "di(", "f()", (0, 2), "a,\n  b"),
        ("f(a,\n  b) z", (0, 2), "da(", "f z", (0, 1), "(a,\n  b)"),
        # Outside a pair: the next one in the note
        ("foo (bar) (baz)", (0, 0), "di(", "foo () (baz)", (0, 5), "bar"),
        ("(a) foo (bar)", (0, 4), "di(", "(a) foo ()", (0, 9), "bar"),
        ("foo\nx [bar]", (0, 1), "da[", "foo\nx ", (1, 1), "[bar]"),
        # passing over an opening that never closes
        ("x ( y (a)", (0, 0), "di(", "x ( y ()", (0, 7), "a"),
    ],
)
def test_the_bracket_objects(text, start, keys, after, cursor, register):
    engine = objects_on(text, start)

    feed(engine, keys)

    assert buffer_of(engine).text == after
    assert buffer_of(engine).cursor == cursor
    assert engine.register == Register(register, linewise=False)
    assert engine.mode == MODE_NORMAL
    assert engine.pending == ""


BLOCK = "if {\n  foo\n  bar\n}\nend"


def test_inside_a_block_on_lines_of_its_own_takes_those_lines():
    engine = objects_on(BLOCK, (1, 3))

    feed(engine, "di{")

    assert buffer_of(engine).text == "if {\n}\nend"
    assert buffer_of(engine).cursor == (1, 0)
    assert engine.register == Register("  foo\n  bar", linewise=True)


def test_changing_inside_a_block_leaves_one_indented_line_to_type_on():
    engine = objects_on(BLOCK, (2, 0))

    feed(engine, "ci{")

    assert buffer_of(engine).text == "if {\n  \n}\nend"
    assert buffer_of(engine).cursor == (1, 2)
    assert engine.mode == MODE_INSERT


def test_changing_inside_a_bracket_pair_types_between_them():
    engine = objects_on("f(a, b) + 1", (0, 4))

    feed(engine, "ci(")

    assert buffer_of(engine).text == "f() + 1"
    assert buffer_of(engine).cursor == (0, 2)
    assert engine.mode == MODE_INSERT


def test_changing_inside_an_empty_pair_still_goes_into_insert():
    engine = objects_on("f()", (0, 1))

    feed(engine, "ci(")

    assert buffer_of(engine).text == "f()"
    assert buffer_of(engine).cursor == (0, 2)
    assert engine.mode == MODE_INSERT


@pytest.mark.parametrize(
    "text, start, keys",
    [
        # No pair here or after
        ("(a) foo", (0, 5), "di("),
        ("f(a", (0, 2), "di("),
        ("f(a", (0, 2), "ci("),
        # A count goes out further than there are pairs
        ("(a)", (0, 1), "d2i("),
        # Nothing between them to take
        ("f()", (0, 1), "di("),
    ],
)
def test_with_no_bracket_pair_to_take_nothing_happens(text, start, keys):
    engine = objects_on(text, start)

    feed(engine, keys)

    assert buffer_of(engine).text == text
    assert buffer_of(engine).cursor == start
    assert engine.register is None
    assert engine.mode == MODE_NORMAL
    assert engine.pending == ""


@pytest.mark.parametrize(
    "text, start, keys, after, cursor, register",
    [
        ('say "hi there" now', (0, 7), 'di"', 'say "" now', (0, 5), "hi there"),
        # `a` takes the blanks after it, or with none, those before it
        ('say "hi" now', (0, 5), 'da"', "say now", (0, 4), '"hi" '),
        ('say "hi"', (0, 5), 'da"', "say", (0, 2), ' "hi"'),
        # Standing on either quote: they pair up from the line's start
        ('"a" "b"', (0, 4), 'di"', '"a" ""', (0, 5), "b"),
        ('"a" "b"', (0, 2), 'di"', '"" "b"', (0, 1), "a"),
        # Between two pairs, the quotes either side, as in vim
        ('"a" x "b"', (0, 4), 'di"', '"a""b"', (0, 3), " x "),
        # Before any quote: the next pair on the line
        ('x "a" "b"', (0, 0), 'di"', 'x "" "b"', (0, 3), "a"),
        # A quote after a backslash is part of the text
        ('"a \\"b\\" c"', (0, 1), 'di"', '""', (0, 1), 'a \\"b\\" c'),
        # The other quotes, and backticks
        ("it is 'ok'", (0, 7), "di'", "it is ''", (0, 7), "ok"),
        ("run `ls -a` now", (0, 6), "da`", "run now", (0, 4), "`ls -a` "),
    ],
)
def test_the_quote_objects(text, start, keys, after, cursor, register):
    engine = objects_on(text, start)

    feed(engine, keys)

    assert buffer_of(engine).text == after
    assert buffer_of(engine).cursor == cursor
    assert engine.register == Register(register, linewise=False)
    assert engine.mode == MODE_NORMAL
    assert engine.pending == ""


def test_changing_inside_quotes_types_between_them():
    engine = objects_on('say "hi there" now', (0, 7))

    feed(engine, 'ci"')

    assert buffer_of(engine).text == 'say "" now'
    assert buffer_of(engine).cursor == (0, 5)
    assert engine.mode == MODE_INSERT


@pytest.mark.parametrize(
    "text, start",
    [
        # Past the last pair on the line
        ('"a" x', (0, 4)),
        # A pair only ever on one line, even with the next quote below
        ('x "a\nb" y', (0, 0)),
        ('"a\nb"', (1, 0)),
        # One quote alone
        ('x "a', (0, 0)),
    ],
)
def test_with_no_quote_pair_on_the_line_nothing_happens(text, start):
    engine = objects_on(text, start)

    feed(engine, 'di"')

    assert buffer_of(engine).text == text
    assert buffer_of(engine).cursor == start
    assert engine.register is None
    assert engine.pending == ""


def test_the_default_alphabet_is_the_vim_flash_one():
    assert VIM_FLASH_ALPHABET == "asdfghjklöqwertzuiopyxcvbnm"


def test_ys_yanks_up_to_the_target_and_stays_put():
    engine = flash_on("xa xb xc", (0, 6))
    engine.keys.set("y", VimOperator.YANK)
    feed(engine, "ysxa")
    feed(engine, labels_of(engine)[(0, 0)] or "")

    assert buffer_of(engine).text == "xa xb xc"
    assert engine.register == Register("xa xb x", linewise=False)
    assert buffer_of(engine).cursor == (0, 0)
    assert engine.mode == MODE_NORMAL


# VISUAL and V-LINE


def visual_keys() -> VimKeymap:
    keys = text_object_keys()
    for key, action in yank_keys()._bindings.items():
        keys.set(key, action)
    keys.set(">", VimOperator.INDENT)
    keys.set("<", VimOperator.UNINDENT)
    keys.set("v", VimCommand.VISUAL)
    keys.set("V", VimCommand.VISUAL_LINE)
    keys.set("o", VimCommand.OPEN_BELOW)
    keys.set("s", VimMotion.VIM_FLASH)
    return keys


def visual_on(text: str, cursor: Tuple[int, int] = (0, 0), **options) -> VimEngine:
    return VimEngine(MemoryBuffer(text, cursor), visual_keys(), **options)


def test_v_and_shift_v_enter_visual_and_v_line_and_tell_the_host():
    engine = visual_on("abc\ndef", (0, 1))

    feed(engine, "v")
    assert engine.mode == MODE_VISUAL
    assert engine.selection == ((0, 1), (0, 1))
    assert buffer_of(engine).selected == ((0, 1), (0, 1), False)

    feed(engine, "V")
    assert engine.mode == MODE_VISUAL_LINE
    assert buffer_of(engine).selected == ((0, 1), (0, 1), True)

    feed(engine, "v")
    assert engine.mode == MODE_VISUAL
    assert buffer_of(engine).modes == [MODE_VISUAL, MODE_VISUAL_LINE, MODE_VISUAL]


@pytest.mark.parametrize("key", ["v", "V"])
def test_the_same_key_again_leaves_for_normal(key):
    engine = visual_on("abc\ndef", (0, 1))

    feed(engine, key + "l" + key)

    assert engine.mode == MODE_NORMAL
    assert engine.selection is None
    assert buffer_of(engine).selected is None
    assert buffer_of(engine).cursor == (1, 1)


def test_escape_leaves_visual_and_is_used():
    engine = visual_on("abc", (0, 1))

    feed(engine, "vö")

    assert engine.feed("escape")
    assert engine.mode == MODE_NORMAL
    assert buffer_of(engine).selected is None
    assert buffer_of(engine).cursor == (0, 2)

    # With nothing left to leave, it's the host's again
    assert not engine.feed("escape")


def test_escape_cancels_a_half_typed_object_before_visual():
    engine = visual_on("abc", (0, 1))

    feed(engine, "vi")
    assert engine.pending == "i"

    engine.feed("escape")
    assert engine.mode == MODE_VISUAL
    assert engine.pending == ""


@pytest.mark.parametrize(
    "text, start, keys, selection",
    [
        ("abc def", (0, 0), "vw", ((0, 0), (0, 4))),
        ("abc def", (0, 0), "v_", ((0, 0), (0, 6))),
        ("abc def", (0, 5), "vb", ((0, 5), (0, 4))),
        ("abc\ndef", (0, 1), "vl", ((0, 1), (1, 1))),
        ("abc def", (0, 0), "vf ", ((0, 0), (0, 3))),
        ("abc def", (0, 0), "v2ö", ((0, 0), (0, 2))),
        # The cursor never goes past the last character
        ("abc", (0, 0), "v9ö", ((0, 0), (0, 2))),
        ("abc\nd", (0, 2), "vl", ((0, 2), (1, 0))),
    ],
)
def test_motions_extend_the_selection(text, start, keys, selection):
    engine = visual_on(text, start)

    feed(engine, keys)

    assert engine.mode == MODE_VISUAL
    assert engine.selection == selection
    assert buffer_of(engine).selected == (*selection, False)
    assert buffer_of(engine).text == text


@pytest.mark.parametrize(
    "text, start, keys, mode, selection",
    [
        ("a { b c } d", (0, 5), "vi{", MODE_VISUAL, ((0, 3), (0, 7))),
        ("a { b c } d", (0, 5), "va{", MODE_VISUAL, ((0, 2), (0, 8))),
        ('say "hi there" ok', (0, 6), 'va"', MODE_VISUAL, ((0, 4), (0, 14))),
        ("foo bar baz", (0, 5), "viw", MODE_VISUAL, ((0, 4), (0, 6))),
        ("a foo.bar(x) b", (0, 4), "viW", MODE_VISUAL, ((0, 2), (0, 11))),
        ("a foo.bar(x) b", (0, 4), "vi ", MODE_VISUAL, ((0, 2), (0, 11))),
        ("one\ntwo\n\nthree", (0, 1), "vip", MODE_VISUAL_LINE, ((0, 0), (1, 0))),
        # Contents on lines of their own are taken as lines, as in vim
        ("f {\n  a\n  b\n}", (1, 2), "vi{", MODE_VISUAL_LINE, ((1, 0), (2, 0))),
    ],
)
def test_text_objects_select_what_they_cover(text, start, keys, mode, selection):
    engine = visual_on(text, start)

    feed(engine, keys)

    assert engine.mode == mode
    assert engine.selection == selection
    assert buffer_of(engine).selected == (*selection, mode == MODE_VISUAL_LINE)
    assert buffer_of(engine).text == text


def test_a_character_object_in_v_line_selects_characters():
    engine = visual_on("foo bar", (0, 5))

    feed(engine, "Viw")

    assert engine.mode == MODE_VISUAL
    assert engine.selection == ((0, 4), (0, 6))


def test_an_object_with_nothing_inside_leaves_the_selection_be():
    engine = visual_on("f() x", (0, 1))

    feed(engine, "vi(")

    assert engine.mode == MODE_VISUAL
    assert engine.selection == ((0, 1), (0, 1))


def test_i_and_a_wait_for_an_object_instead_of_inserting():
    engine = visual_on("abc", (0, 1))

    feed(engine, "vi")
    assert engine.mode == MODE_VISUAL
    feed(engine, "a")
    assert engine.mode == MODE_VISUAL
    assert buffer_of(engine).text == "abc"


def test_o_goes_to_the_other_end():
    engine = visual_on("abc def", (0, 1))

    feed(engine, "vwo")

    assert engine.selection == ((0, 4), (0, 1))
    assert buffer_of(engine).cursor == (0, 1)

    feed(engine, "o")
    assert engine.selection == ((0, 1), (0, 4))


@pytest.mark.parametrize(
    "text, start, keys, after, cursor, register",
    [
        # Both ends are taken, whichever way it was made
        ("abc def", (0, 1), "vöd", "a def", (0, 1), "bc"),
        ("abc def", (0, 2), "vjd", "a def", (0, 1), "bc"),
        ("abc def", (0, 1), "vöx", "a def", (0, 1), "bc"),
        ("abc\ndef", (0, 1), "vld", "af", (0, 1), "bc\nde"),
        # The last character, and from an empty line its line break
        ("abc", (0, 1), "v_d", "a", (0, 0), "bc"),
        ("a\n\nb", (0, 0), "vld", "b", (0, 0), "a\n\n"),
        ("abc\ndef\nghi", (1, 1), "Vd", "abc\nghi", (1, 1), "def"),
        ("abc\ndef\nghi", (0, 1), "Vld", "ghi", (0, 1), "abc\ndef"),
        ("abc\ndef\nghi", (2, 1), "Vkd", "abc", (0, 1), "def\nghi"),
    ],
)
def test_delete_takes_the_selection(text, start, keys, after, cursor, register):
    engine = visual_on(text, start)

    feed(engine, keys)

    assert buffer_of(engine).text == after
    assert buffer_of(engine).cursor == cursor
    assert engine.mode == MODE_NORMAL
    assert buffer_of(engine).selected is None
    assert engine.register is not None
    assert engine.register.text == register
    assert engine.register.linewise == keys.startswith("V")


@pytest.mark.parametrize(
    "start, keys, register, linewise, cursor",
    [
        ((0, 3), "vby", "abc ", False, (0, 0)),
        ((0, 0), "viwy", "abc", False, (0, 0)),
        ((1, 2), "Vky", "abc def\nxyz", True, (0, 2)),
    ],
)
def test_yank_copies_the_selection_and_goes_to_its_start(
    start, keys, register, linewise, cursor
):
    engine = visual_on("abc def\nxyz", start)

    feed(engine, keys)

    assert buffer_of(engine).text == "abc def\nxyz"
    assert engine.register == Register(register, linewise)
    assert buffer_of(engine).clipboard == register
    assert buffer_of(engine).cursor == cursor
    assert engine.mode == MODE_NORMAL


def test_change_takes_the_selection_and_types_in_its_place():
    engine = visual_on("abc def", (0, 4))

    feed(engine, "viwc")
    assert engine.mode == MODE_INSERT
    assert buffer_of(engine).text == "abc "
    assert buffer_of(engine).cursor == (0, 4)
    assert engine.register == Register("def", False)


def test_change_on_lines_keeps_the_first_ones_marker():
    engine = visual_on("- one\n- two\nthree", (0, 3))

    feed(engine, "Vlc")

    assert engine.mode == MODE_INSERT
    assert buffer_of(engine).text == "- \nthree"
    assert buffer_of(engine).cursor == (0, 2)


@pytest.mark.parametrize(
    "keys, after",
    [
        ("Vl>", "    a\n    b\nc"),
        ("vl>", "    a\n    b\nc"),
        ("Vl2>", "      a\n      b\nc"),
        ("Vl<", "a\nb\nc"),
    ],
)
def test_indenting_the_selection_returns_to_normal(keys, after):
    engine = visual_on("  a\n  b\nc", (0, 2))

    feed(engine, keys)

    assert buffer_of(engine).text == after
    assert engine.mode == MODE_NORMAL
    assert buffer_of(engine).selected is None


def test_every_selection_edit_is_one_undo_step():
    engine = visual_on("abc def\nxyz", (0, 0))

    feed(engine, "vwld")
    assert buffer_of(engine).text == ""

    feed(engine, "u")
    assert buffer_of(engine).text == "abc def\nxyz"


@pytest.mark.parametrize(
    "text, start, yank, keys, after, cursor, register",
    [
        # Characters over characters, the selection going to the register
        ("ab cd", (0, 0), "yiw", "wviwp", "ab ab", (0, 4), "cd"),
        # `P` keeps the register as it was
        ("ab cd", (0, 0), "yiw", "wviwP", "ab ab", (0, 4), "ab"),
        # Lines over lines
        ("ab\ncd\nef", (0, 0), "yy", "lVlp", "ab\nab", (1, 0), "cd\nef"),
        # Lines over characters go on lines of their own
        ("ab\ncd", (0, 0), "yy", "lvp", "ab\n\nab\nd", (2, 0), "c"),
        # Characters over lines take their place
        ("ab\ncd", (0, 0), "yiw", "lVp", "ab\nab", (1, 0), "cd"),
        # A count puts in that many
        ("ab cd", (0, 0), "yiw", "wviw2p", "ab abab", (0, 6), "cd"),
    ],
)
def test_p_replaces_the_selection(text, start, yank, keys, after, cursor, register):
    engine = visual_on(text, start)

    feed(engine, yank)
    feed(engine, keys)

    assert buffer_of(engine).text == after
    assert buffer_of(engine).cursor == cursor
    assert engine.mode == MODE_NORMAL
    assert engine.register is not None
    assert engine.register.text == register


def test_p_over_a_selection_pastes_a_new_clipboard_the_hosts_way():
    engine = visual_on("ab cd", (0, 3))
    buffer_of(engine).clipboard = "XY"

    feed(engine, "viwp")

    assert buffer_of(engine).text == "ab XY"
    assert buffer_of(engine).clipboard_pastes == ["XY"]
    assert engine.mode == MODE_NORMAL
    assert buffer_of(engine).cursor == (0, 4)


def test_p_with_nothing_to_paste_says_so_and_leaves_visual():
    engine = visual_on("ab", (0, 0))

    feed(engine, "vp")

    assert buffer_of(engine).text == "ab"
    assert buffer_of(engine).reports == ["Nothing to paste"]
    assert engine.mode == MODE_NORMAL


def test_commands_with_no_meaning_on_a_selection_do_nothing():
    engine = visual_on("abc", (0, 0))

    feed(engine, "vöIAsr")

    assert engine.mode == MODE_VISUAL
    assert buffer_of(engine).text == "abc"
    assert engine.selection == ((0, 0), (0, 1))


def test_a_search_extends_the_selection():
    engine = visual_on("abc def abc", (0, 0))

    feed(engine, "v?def")
    assert engine.selection == ((0, 0), (0, 4))
    engine.feed("enter")

    assert engine.mode == MODE_VISUAL
    assert engine.selection == ((0, 0), (0, 4))
    assert buffer_of(engine).selected == ((0, 0), (0, 4), False)


def test_a_host_selection_enters_visual_and_carries_on():
    engine = visual_on("abc def", (0, 0))
    buffer = buffer_of(engine)

    # As a drag can leave it: its end past the last character
    engine.select_between((0, 2), (0, 7))

    assert engine.mode == MODE_VISUAL
    assert engine.selection == ((0, 2), (0, 6))
    assert buffer.selected == ((0, 2), (0, 6), False)

    engine.select_between((0, 2), (0, 4))
    assert engine.selection == ((0, 2), (0, 4))

    feed(engine, "d")
    assert buffer.text == "abef"


def test_a_host_selection_in_v_line_stays_lines():
    engine = visual_on("abc\ndef", (0, 1))

    feed(engine, "V")
    engine.select_between((0, 1), (1, 1))

    assert engine.mode == MODE_VISUAL_LINE
    assert buffer_of(engine).selected == ((0, 1), (1, 1), True)


def test_undo_in_visual_leaves_it_and_undoes():
    engine = visual_on("abc", (0, 0))

    feed(engine, "x")
    feed(engine, "vu")

    assert engine.mode == MODE_NORMAL
    assert buffer_of(engine).text == "abc"


def test_a_host_on_one_line_has_no_v_line():
    engine = visual_on("abc", (0, 0), multiline=False)

    assert not engine.feed("V")
    assert engine.mode == MODE_NORMAL

    feed(engine, "vöd")
    assert buffer_of(engine).text == "c"


# vim_flash in VISUAL and V-LINE


def test_s_in_visual_extends_the_selection_to_the_target():
    engine = visual_on("xa xb xc", (0, 1))
    feed(engine, "vösxc")
    assert engine.mode == MODE_FLASH

    feed(engine, labels_of(engine)[(0, 6)] or "")

    assert engine.mode == MODE_VISUAL
    assert engine.selection == ((0, 1), (0, 6))
    assert buffer_of(engine).selected == ((0, 1), (0, 6), False)
    assert buffer_of(engine).text == "xa xb xc"
    assert engine.register is None
    assert engine.pending == ""


def test_s_in_visual_goes_backward_past_where_it_started():
    engine = visual_on("xa xb xc", (0, 4))
    feed(engine, "vsxa")
    feed(engine, labels_of(engine)[(0, 0)] or "")

    assert engine.mode == MODE_VISUAL
    assert engine.selection == ((0, 4), (0, 0))

    feed(engine, "d")
    assert buffer_of(engine).text == " xc"


def test_s_in_v_line_extends_by_lines_and_an_operator_takes_them():
    engine = visual_on("aa\nbb\ncc\ndd", (0, 0))
    feed(engine, "Vsc")
    engine.feed("enter")

    assert engine.mode == MODE_VISUAL_LINE
    assert engine.selection == ((0, 0), (2, 0))
    assert buffer_of(engine).selected == ((0, 0), (2, 0), True)

    feed(engine, "d")
    assert buffer_of(engine).text == "dd"
    assert engine.register == Register("aa\nbb\ncc", linewise=True)


def test_escape_in_vim_flash_goes_back_to_the_selection_as_it_was():
    engine = visual_on("xa xb xc", (0, 1))
    feed(engine, "vösx")

    assert engine.feed("escape")
    assert engine.mode == MODE_VISUAL
    assert engine.selection == ((0, 1), (0, 2))
    assert buffer_of(engine).selected == ((0, 1), (0, 2), False)
    assert buffer_of(engine).cursor == (0, 2)
    assert engine.vim_flash_view is None

    # The next one leaves VISUAL, as ever
    assert engine.feed("escape")
    assert engine.mode == MODE_NORMAL


def test_nothing_left_to_go_to_in_v_line_keeps_the_selection():
    engine = visual_on("aa\nbb", (0, 1))
    feed(engine, "Vsq")

    assert engine.mode == MODE_VISUAL_LINE
    assert engine.selection == ((0, 1), (0, 1))
    assert buffer_of(engine).cursor == (0, 1)


def test_escape_in_vim_flash_after_y_drops_the_yank():
    engine = flash_on("xa xb", (0, 3))
    engine.keys.set("y", VimOperator.YANK)
    feed(engine, "ysx")
    engine.feed("escape")

    assert engine.mode == MODE_NORMAL
    assert engine.pending == ""
    assert engine.register is None
    assert buffer_of(engine).cursor == (0, 3)


def test_cs_backward_changes_back_to_the_target_with_the_cursors_character():
    engine = flash_on("xa xb xc", (0, 4))
    engine.keys.set("c", VimOperator.CHANGE)
    feed(engine, "csxa")
    feed(engine, labels_of(engine)[(0, 0)] or "")

    assert buffer_of(engine).text == " xc"
    assert buffer_of(engine).cursor == (0, 0)
    assert engine.mode == MODE_INSERT
    assert engine.register == Register("xa xb", linewise=False)


# --- The yanked range, for a host to flash ------------------------------------


@pytest.mark.parametrize(
    "text, start, keys, yanked",
    [
        # charwise, with motions
        ("ab cd", (0, 0), "yw", ((0, 0), (0, 3), False)),
        ("ab cd", (0, 3), "yb", ((0, 0), (0, 3), False)),
        ("ab cd", (0, 0), "ye", ((0, 0), (0, 2), False)),
        ("ab cd", (0, 0), "yf ", ((0, 0), (0, 3), False)),
        # a text object
        ("ab cd", (0, 3), "yiw", ((0, 3), (0, 5), False)),
        # linewise: whole lines, from the first's start to the last's end
        ("aa\nbb\ncc", (1, 1), "yy", ((1, 0), (1, 2), True)),
        ("aa\nbb\ncc", (0, 1), "2yy", ((0, 0), (1, 2), True)),
        ("aa\nbb\ncc", (1, 1), "yk", ((0, 0), (1, 2), True)),
        ("aa\nbb\ncc", (0, 0), "yG", ((0, 0), (2, 2), True)),
    ],
)
def test_a_yank_reports_the_range_it_took(text, start, keys, yanked):
    engine = visual_on(text, start)

    feed(engine, keys)

    assert buffer_of(engine).text == text
    assert engine.mode == MODE_NORMAL
    assert engine.yanked == YankedRange(*yanked)


@pytest.mark.parametrize(
    "text, start, keys, yanked, register",
    [
        ("abc def", (0, 1), "vöy", ((0, 1), (0, 3), False), "bc"),
        ("abc def", (0, 2), "vjy", ((0, 1), (0, 3), False), "bc"),
        ("abc\ndef", (0, 1), "vly", ((0, 1), (1, 2), False), "bc\nde"),
        ("aa\nbb\ncc", (0, 1), "Vly", ((0, 0), (1, 2), True), "aa\nbb"),
    ],
)
def test_a_visual_yank_reports_what_was_selected_back_in_normal(
    text, start, keys, yanked, register
):
    engine = visual_on(text, start)

    feed(engine, keys)

    assert engine.mode == MODE_NORMAL
    assert engine.selection is None
    assert engine.register is not None
    assert engine.register.text == register
    assert engine.yanked == YankedRange(*yanked)


@pytest.mark.parametrize("keys", ["dw", "dd", "x", "cw", "cc", "C", "D", "vöd", "Vx"])
def test_deleting_and_changing_report_no_yank_and_leave_the_clipboard_alone(keys):
    engine = visual_on("ab cd\nef", (0, 0))
    buffer_of(engine).clipboard = "from elsewhere"

    feed(engine, keys)

    assert engine.register is not None
    assert engine.yanked is None
    assert buffer_of(engine).clipboard == "from elsewhere"


def test_the_yanked_range_lasts_only_until_the_next_key():
    engine = visual_on("ab cd", (0, 0))

    feed(engine, "yw")
    assert engine.yanked is not None

    feed(engine, "ö")
    assert engine.yanked is None

    # A key that only starts a command clears it too
    feed(engine, "yw")
    feed(engine, "y")
    assert engine.yanked is None


def test_a_yank_that_takes_nothing_reports_nothing():
    engine = visual_on("abc")

    feed(engine, "yfz")
    assert engine.yanked is None


# --- The help, left to the host -----------------------------------------------


@pytest.mark.parametrize("before, mode", [("", MODE_NORMAL), ("v", MODE_VISUAL)])
def test_space_question_mark_asks_the_host_for_the_help(before, mode):
    engine = visual_on("abc def", (0, 1))
    engine.keys.set(" ?", VimCommand.HELP)

    feed(engine, before + " ?")

    assert buffer_of(engine).helps_shown == 1
    assert engine.mode == mode
    assert buffer_of(engine).cursor == (0, 1)
    assert buffer_of(engine).text == "abc def"
    assert engine.pending == ""


def test_space_alone_waits_for_the_question_mark():
    engine = visual_on("abc def")
    engine.keys.set(" ?", VimCommand.HELP)

    feed(engine, " ")
    assert engine.pending == " "
    assert buffer_of(engine).helps_shown == 0

    feed(engine, "w")
    assert engine.pending == ""
    assert buffer_of(engine).helps_shown == 0


# --- Only some of vim, for a host that wants no more ---------------------------


def test_an_action_left_out_is_left_to_the_host_as_if_unbound():
    engine = visual_on(
        "abc def", (0, 1), actions=frozenset({VimMotion.RIGHT, VimOperator.DELETE})
    )

    assert engine.feed("y") is False
    assert engine.feed("v") is False
    assert engine.mode == MODE_NORMAL
    assert engine.pending == ""

    # What is in still works
    assert engine.feed("ö") is True
    assert buffer_of(engine).cursor == (0, 2)


def test_an_action_left_out_behind_an_operator_only_cancels_it():
    engine = visual_on(
        "abc def", (0, 0), actions=frozenset({VimOperator.DELETE, VimMotion.WORD_FORWARD})
    )

    feed(engine, "d")
    assert engine.pending == "d"

    # `e`, `iw` and `dd` all mean something, but not to this host
    feed(engine, "e")
    assert engine.pending == ""
    feed(engine, "diw")
    feed(engine, "dd")

    assert buffer_of(engine).text == "abc def"
    assert engine.register is None

    feed(engine, "dw")
    assert buffer_of(engine).text == "def"


def test_with_no_actions_given_everything_is_bound():
    engine = visual_on("abc def")

    feed(engine, "yw")
    assert engine.register == Register("abc ", linewise=False)

    feed(engine, "v")
    assert engine.mode == MODE_VISUAL


def test_the_description_actions_leave_out_yank_visual_search_and_undo():
    left_out = {
        VimOperator.YANK,
        VimCommand.YANK_LINE,
        VimCommand.VISUAL,
        VimCommand.VISUAL_LINE,
        VimCommand.SEARCH,
        VimCommand.SEARCH_WORD,
        VimCommand.REPLACE_MATCHES,
        VimMotion.SEARCH_NEXT,
        VimMotion.SEARCH_PREVIOUS,
        VimMotion.VIM_FLASH,
        VimCommand.INSERT_AT_LAST,
        VimCommand.OPEN_LINK,
        VimCommand.PICK_FILES,
        VimCommand.HELP,
        VimCommand.UNDO,
        VimCommand.REDO,
    }

    assert not DESCRIPTION_ACTIONS & (left_out | LINE_ONLY)


def lines_in_register(text: str) -> RegisterMemory:
    return RegisterMemory(Register(text, linewise=True), known_clipboard="")


@pytest.mark.parametrize(
    "keys, after, cursor",
    [("p", "abone two cd", (0, 8)), ("P", "aone twob cd", (0, 7))],
)
def test_a_single_line_host_pastes_lines_as_one_line_of_characters(keys, after, cursor):
    engine = yanking_on(
        "ab cd", (0, 1), multiline=False, register_memory=lines_in_register("one\ntwo")
    )

    feed(engine, keys)

    assert buffer_of(engine).text == after
    assert buffer_of(engine).cursor == cursor


def test_a_note_still_pastes_lines_as_lines():
    engine = yanking_on("ab cd", (0, 1), register_memory=lines_in_register("one\ntwo"))

    feed(engine, "p")

    assert buffer_of(engine).text == "ab cd\none\ntwo"
    assert buffer_of(engine).cursor == (1, 0)
