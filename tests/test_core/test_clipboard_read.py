"""
Reading the clipboard in the background, for a key that mustn't wait for it
"""

from threading import Event
from typing import Iterator, List
from unittest.mock import patch

import pytest

from todooit.utils import clipboard, copy_text, start_reading_text


class SlowClipboard:
    """A clipboard that is read the moment it's asked, but answers only when told."""

    def __init__(self) -> None:
        self.text = "before"
        self.reads = 0
        self.begun = Event()
        self.answer = Event()

    def paste(self) -> str:
        self.reads += 1
        text = self.text
        self.begun.set()
        assert self.answer.wait(10)
        return text


@pytest.fixture
def slow() -> Iterator[SlowClipboard]:
    host = SlowClipboard()

    with (
        patch.object(clipboard, "_reading", None),
        patch("todooit.utils.clipboard.pyperclip.paste", host.paste),
        patch("todooit.utils.clipboard.pyperclip.copy", lambda text: None),
    ):
        yield host
        host.answer.set()


def test_it_gives_what_was_there_when_it_started(slow: SlowClipboard):
    read = start_reading_text()
    assert slow.begun.wait(10)

    slow.text = "after"
    slow.answer.set()

    assert read.text() == "before"


def test_one_still_running_is_shared(slow: SlowClipboard):
    first = start_reading_text()

    assert start_reading_text() is first

    slow.answer.set()
    first.text()
    assert start_reading_text() is not first


def test_a_copy_of_our_own_starts_a_new_one(slow: SlowClipboard):
    first = start_reading_text()
    copy_text(None, "ours")

    assert start_reading_text() is not first


def test_a_clipboard_that_cant_be_read_is_empty():
    failures: List[str] = []

    def fail() -> str:
        failures.append("asked")
        raise RuntimeError("no clipboard tool")

    with (
        patch.object(clipboard, "_reading", None),
        patch("todooit.utils.clipboard.pyperclip.paste", fail),
    ):
        assert start_reading_text().text() == ""

    assert failures
