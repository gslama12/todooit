"""
Paths on disk: how one is recognised, what it means here, and who opens it
"""

from pathlib import Path

import pytest

from todooit.utils import files
from todooit.utils.files import (
    GENERIC_ICON,
    Opened,
    display_name,
    file_icon,
    looks_like_path,
    open_path,
    read_attachments,
    resolve_path,
    to_windows,
    to_wsl,
    write_attachments,
)


@pytest.fixture(autouse=True)
def fresh_openers():
    """
    Both cached answers are about the machine, and the tests lie about it
    """

    files.openers.cache_clear()
    files.is_wsl.cache_clear()

    yield

    files.openers.cache_clear()
    files.is_wsl.cache_clear()


def test_the_four_ways_a_path_is_written():
    assert looks_like_path("/mnt/c/data/notes.md")
    assert looks_like_path("C:\\Users\\me\\a.pdf")
    assert looks_like_path("~/Documents/spec.pdf")
    assert looks_like_path("file:///mnt/c/a%20b.pdf")

    # Spaces and all: files are called things like `Q3 report.pdf`
    assert looks_like_path("/mnt/c/Q3 report.pdf")


def test_a_sentence_is_not_a_path():
    """
    Nothing scans inside a line: a path is a whole line or it is words
    """

    assert not looks_like_path("the file is in /mnt/c/data/notes.md")
    assert not looks_like_path("and/or")
    assert not looks_like_path("later thing")
    assert not looks_like_path("https://example.com/docs/page")


def test_a_file_uri_comes_back_as_a_plain_path():
    assert resolve_path("file:///mnt/c/Q3%20report.pdf") == Path(
        "/mnt/c/Q3 report.pdf"
    )


def test_a_windows_uri_keeps_its_drive():
    assert resolve_path("file:///C:/Users/me/a.pdf") == Path("/mnt/c/Users/me/a.pdf")


def test_a_tilde_is_where_home_is(monkeypatch):
    monkeypatch.setenv("HOME", "/home/someone")

    assert resolve_path("~/notes.md") == Path("/home/someone/notes.md")


def test_something_that_is_not_a_path_resolves_to_nothing():
    assert resolve_path("https://example.com") is None
    assert resolve_path("   ") is None


def test_the_two_translations_without_wslpath(monkeypatch):
    # The pure-python fallback, which is the default WSL layout written out
    monkeypatch.setattr(files, "which", lambda name: None)

    assert to_wsl("C:\\Users\\me\\a.pdf") == "/mnt/c/Users/me/a.pdf"
    assert to_wsl("/already/posix") == "/already/posix"
    assert to_windows(Path("/mnt/c/Users/me/a.pdf")) == "C:\\Users\\me\\a.pdf"


def test_the_icon_says_what_kind_of_file_it_is():
    assert file_icon("Q3 report.pdf") == file_icon("other.PDF")
    assert file_icon("a.pdf") != file_icon("a.png")
    assert file_icon("a.whatever") == GENERIC_ICON


def test_a_file_is_called_by_its_name():
    assert display_name("/mnt/c/Users/me/Q3 report.pdf") == "Q3 report.pdf"
    assert display_name("file:///mnt/c/a%20b.pdf") == "a b.pdf"


def test_a_file_that_is_not_there_is_not_handed_to_anybody(monkeypatch):
    handed = []

    monkeypatch.setattr(files, "spawn", lambda argv: handed.append(argv) or True)

    assert open_path(Path("/nowhere/at/all.pdf")) is Opened.MISSING
    assert handed == []


@pytest.fixture
def attachment(tmp_path):
    path = tmp_path / "Q3 report.pdf"
    path.write_text("not really a pdf")

    return path


def opener_used(monkeypatch, system: str, wsl: bool, available: tuple):
    """Run an open with only `available` installed, and report the argv"""

    handed = []

    monkeypatch.setattr(files.platform, "system", lambda: system)
    monkeypatch.setattr(files, "is_wsl", lambda: wsl)
    monkeypatch.setattr(
        files, "which", lambda name: f"/usr/bin/{name}" if name in available else None
    )
    monkeypatch.setattr(files, "spawn", lambda argv: handed.append(argv) or True)

    # The answer is cached, and everything above has just changed it
    files.openers.cache_clear()

    return handed


def test_a_mac_opens_with_open(monkeypatch, attachment):
    handed = opener_used(monkeypatch, "Darwin", False, ("open", "xdg-open"))

    assert open_path(attachment) is Opened.OK
    assert handed == [["/usr/bin/open", str(attachment)]]


def test_a_plain_linux_opens_with_xdg_open(monkeypatch, attachment):
    handed = opener_used(monkeypatch, "Linux", False, ("xdg-open",))

    assert open_path(attachment) is Opened.OK
    assert handed == [["/usr/bin/xdg-open", str(attachment)]]


def test_a_windows_opener_is_handed_a_windows_path(monkeypatch, attachment):
    handed = opener_used(monkeypatch, "Linux", True, ("rundll32.exe",))
    monkeypatch.setattr(files, "to_windows", lambda path: "Z:\\somewhere")

    assert open_path(attachment) is Opened.OK
    assert handed == [
        [
            "/usr/bin/rundll32.exe",
            "url.dll,FileProtocolHandler",
            "Z:\\somewhere",
        ]
    ]


def test_nothing_installed_is_said_rather_than_swallowed(monkeypatch, attachment):
    opener_used(monkeypatch, "Linux", False, ())

    assert open_path(attachment) is Opened.NO_OPENER



def test_the_column_is_one_path_per_line():
    paths = [Path("/a/b.pdf"), Path("/c/Q3 report.md")]

    assert write_attachments(paths) == "/a/b.pdf\n/c/Q3 report.md"
    assert read_attachments(write_attachments(paths)) == paths


def test_a_line_that_is_no_longer_a_path_is_dropped():
    """A column edited by hand, or written by something else, still reads"""

    assert read_attachments("/a/b.pdf\n\nnot a path\n~/c.md") == [
        Path("/a/b.pdf"),
        Path.home() / "c.md",
    ]


def test_the_same_file_twice_is_held_once():
    assert read_attachments("/a/b.pdf\n/a/b.pdf") == [Path("/a/b.pdf")]
