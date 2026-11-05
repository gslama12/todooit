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
    VimCommand,
    VimEngine,
    VimKeymap,
    VimMotion,
)


class MemoryBuffer:
    """The smallest host there is: lines of text and a cursor."""

    def __init__(self, text: str, cursor: Tuple[int, int] = (0, 0)) -> None:
        self.lines: List[str] = text.split("\n")
        self.cursor = cursor
        self.modes: List[str] = []

    @property
    def line_count(self) -> int:
        return len(self.lines)

    def line(self, row: int) -> str:
        return self.lines[row]

    def move_cursor(self, row: int, column: int) -> None:
        self.cursor = (row, column)

    def move_rows(self, delta: int) -> None:
        row = max(0, min(self.cursor[0] + delta, self.line_count - 1))
        self.cursor = (row, min(self.cursor[1], len(self.lines[row])))

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

    assert engine.feed("z") is False
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
