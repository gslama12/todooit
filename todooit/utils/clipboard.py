"""
The clipboard, as far as a terminal application can reach it

Two channels, because neither one covers the ground on its own: textual writes
through the terminal itself (an OSC 52 escape), which is what carries a copy
out of an ssh session or out of WSL, while pyperclip talks to the host's own
clipboard - and is the only one of the two that can *read* it back.

And then a third way in, for the one thing neither can see: a *file* copied in
a file manager, which is on the clipboard as a file and not as any text at all.
"""

import platform
from shutil import which
from subprocess import DEVNULL, PIPE, SubprocessError, run
from typing import TYPE_CHECKING, List, Optional

import pyperclip

from todooit.utils.files import is_wsl

if TYPE_CHECKING:  # pragma: no cover
    from textual.app import App


def running_app() -> Optional["App"]:
    """
    The app this call is running inside, for code that is handed no app

    A text field is a plain object rather than a widget: it is handed
    keystrokes and nothing else, so the only way it can reach the terminal
    channel is to ask which app it is running in.
    """

    from textual._context import active_app

    return active_app.get(None)


def copy_text(app: Optional["App"], text: str) -> None:
    """
    Put `text` on the clipboard, by both routes
    """

    app = app or running_app()

    if app is not None:
        app.copy_to_clipboard(text)

    try:
        pyperclip.copy(text)
    except Exception:
        # No clipboard tool on the host (no xclip, no clip.exe, ...). The
        # terminal was still handed the text, so the copy is not lost - and a
        # failure here is nothing the user asked about
        pass


def paste_text(app: Optional["App"] = None) -> str:
    """
    What is on the clipboard, or "" if there is nothing to be had

    Falls back to textual's own clipboard, which holds whatever todooit last
    copied, so a copy and paste inside todooit works even on a host with no
    clipboard tool at all.
    """

    app = app or running_app()

    try:
        text = str(pyperclip.paste())
    except Exception:
        text = ""

    if text:
        return text

    return app.clipboard if app is not None else ""


# What is asked of the desktop to read a *file* off the clipboard, per
# platform, and how what comes back is cut into paths.
#
# A file copied in the Finder or in Explorer puts no text on the clipboard at
# all - it puts the file itself there, in a format `pyperclip` cannot see - so
# this is the only way a plain copy-and-paste of a file can work. It is a
# whole process spawned per call, which is why it is only ever reached once
# the text clipboard has already come back empty: the cost is paid on exactly
# the paste that would otherwise do nothing
_FILE_READERS = {
    # AppleScript's name for a file reference. This answers for the one file
    # the clipboard holds; several files copied at once are attached by
    # copying them as text paths instead (`cmd+alt+c` in the Finder), which
    # arrives as one path per line and never gets this far
    "Darwin": (
        "osascript",
        "-e",
        "POSIX path of (the clipboard as «class furl»)",
    ),
    # Windows hands back the whole list, so several files at once work here
    "WSL": (
        "powershell.exe",
        "-NoProfile",
        "-NonInteractive",
        "-Command",
        "Get-Clipboard -Format FileDropList | ForEach-Object { $_.FullName }",
    ),
    # The freedesktop way of saying the same thing: a list of file:// URIs
    "Linux": ("xclip", "-selection", "clipboard", "-t", "text/uri-list", "-o"),
}

# Long enough for a cold `powershell.exe` under WSL, short enough that a
# keystroke never looks like a hang
_READ_TIMEOUT = 5


def _reader() -> Optional[tuple]:
    """
    The command this machine reads copied files with, if it has one
    """

    if platform.system() == "Darwin":
        return _FILE_READERS["Darwin"]

    if is_wsl():
        return _FILE_READERS["WSL"]

    return _FILE_READERS["Linux"]


def paste_files() -> List[str]:
    """
    The files on the clipboard, as paths; empty when there are none

    Failure of any kind - no such program, a timeout, a clipboard holding
    something that is not a file - is the same answer as an empty clipboard.
    Nothing here is worth a message: the paste that asked simply goes on to
    mean what it has always meant.
    """

    command = _reader()

    if command is None or which(command[0]) is None:
        return []

    try:
        done = run(
            list(command),
            stdout=PIPE,
            stderr=DEVNULL,
            stdin=DEVNULL,
            timeout=_READ_TIMEOUT,
            text=True,
        )
    except (OSError, ValueError, SubprocessError):
        return []

    if done.returncode != 0:
        return []

    return [line.strip() for line in done.stdout.splitlines() if line.strip()]
