"""
Files on disk, as a note can point at them

A note never holds a file - it holds the way back to one. What is written in
it is a path and nothing else, so attaching costs nothing, the same file can
be pointed at from as many notes as there are reasons to, and nothing in the
database ever goes stale except the answer to "is it still there", which is
asked afresh every time one is opened.

Three things live here, and they are here rather than in `links.py` because
none of them is about links: what a path looks like when it is written down,
what it means on the machine this is running on, and how the desktop is asked
to open one.
"""

import os
import platform
import re
from dataclasses import dataclass
from enum import Enum
from functools import lru_cache
from pathlib import Path
from shutil import which
from subprocess import DEVNULL, PIPE, Popen, run
from typing import List, Optional, Sequence, Tuple
from urllib.parse import unquote

# A drive letter and the separator after it: the head of a path written the
# way Windows writes one. Either slash, because a path copied out of a browser
# or a config file is as likely to lean forwards as back
_DRIVE = r"[A-Za-z]:[\\/]"

# A whole line that is a path and nothing else, which is the only way a path
# is ever read here: a file is attached by being pasted, and a paste is either
# paths or it is text.
#
# Nothing scans for a path written inside a sentence. A note holds no
# attachments - they are kept beside it rather than in it - so a `/usr/local`
# written in the middle of a line is a word in a sentence, and is left as one.
#
# Used with `fullmatch`, and spaces are allowed because files are called
# things like `Q3 report.pdf`
PATH_RE = re.compile(rf"(?:file://\S*|{_DRIVE}[^\n]*|~/[^\n]*|/[^\n]+)")


@lru_cache(maxsize=1)
def is_wsl() -> bool:
    """
    Whether this is Linux running under Windows

    Which matters for exactly one thing: on WSL the desktop that opens a file
    is on the other side of a translation, and the path has to be written the
    way Windows writes one before it is handed over.
    """

    if os.environ.get("WSL_DISTRO_NAME"):
        return True

    try:
        release = Path("/proc/sys/kernel/osrelease").read_text()
    except OSError:
        return False

    return "microsoft" in release.lower()


def _mounted(drive: str) -> str:
    """
    Where a Windows drive is mounted, by the default WSL layout
    """

    return f"/mnt/{drive.lower()}"


def to_wsl(text: str) -> str:
    """
    A path written the Windows way, as the same path seen from Linux

    `wslpath` is asked first, because it knows where the drives are actually
    mounted and this does not. The fallback is the default layout - `C:\\x`
    under `/mnt/c/x` - which is right on every machine that has not been told
    otherwise, and is what keeps this callable, and testable, off WSL.
    """

    if not re.match(_DRIVE, text):
        return text

    if which("wslpath"):
        try:
            done = run(
                ["wslpath", "-u", text],
                stdout=PIPE,
                stderr=DEVNULL,
                stdin=DEVNULL,
                timeout=5,
                text=True,
            )

            if done.returncode == 0 and done.stdout.strip():
                return done.stdout.strip()
        except (OSError, ValueError):
            pass

    return _mounted(text[0]) + "/" + text[3:].replace("\\", "/")


def to_windows(path: Path) -> str:
    """
    A path seen from Linux, as the same path written the Windows way

    The other direction, for handing one to a Windows program. `wslpath -w`
    answers for a file inside the Linux filesystem too, where the answer is a
    `\\\\wsl.localhost\\...` share - which is how a note attached to a file
    that never leaves WSL still opens in a Windows application.

    It is a translation and not a lookup: it answers for a path that is not
    there, which is why the "is it still there" check can be left until after.
    """

    text = str(path)

    if which("wslpath"):
        try:
            done = run(
                ["wslpath", "-w", text],
                stdout=PIPE,
                stderr=DEVNULL,
                stdin=DEVNULL,
                timeout=5,
                text=True,
            )

            if done.returncode == 0 and done.stdout.strip():
                return done.stdout.strip()
        except (OSError, ValueError):
            pass

    match = re.match(r"/mnt/([A-Za-z])(?=/|$)", text)

    if match:
        rest = text[match.end() :].replace("/", "\\")

        return f"{match.group(1).upper()}:{rest or chr(92)}"

    return text.replace("/", "\\")


def resolve_path(target: str) -> Optional[Path]:
    """
    Whatever was written, as the one path the rest of the code works in

    Four ways in and one way out. A `file://` URI has its scheme taken off and
    its escapes read back, a Windows path is translated, a `~` is expanded,
    and a plain absolute path is already there. None of it touches the disk:
    this says what was *meant*, not whether it exists.
    """

    text = target.strip().strip("\"'").strip()

    if not text:
        return None

    if text.lower().startswith("file://"):
        text = unquote(text[len("file://") :])

        # `file:///C:/x` - the host is empty and the drive is what follows, so
        # the slash in front of it is the URI's and not the path's
        if re.match(rf"/{_DRIVE}", text):
            text = text[1:]

    if re.match(_DRIVE, text):
        text = to_wsl(text)

    if text.startswith("~"):
        text = os.path.expanduser(text)

    if not text.startswith("/"):
        return None

    return Path(text)


def looks_like_path(target: str) -> bool:
    """
    Whether `target` is written as a path rather than as an address
    """

    return bool(PATH_RE.fullmatch(target.strip()))


# What a file is drawn with, by what it is. One family of glyphs throughout -
# the sheet of paper with a mark on it - so that a list of attachments reads
# as a list of files first and as a list of kinds second
GENERIC_ICON = "\uf15b"

FILE_ICONS = {
    "\uf1c1": ("pdf",),
    "\uf1c2": ("doc", "docx", "odt", "rtf", "pages"),
    "\uf1c3": ("xls", "xlsx", "csv", "tsv", "ods", "numbers"),
    "\uf1c4": ("ppt", "pptx", "odp", "key"),
    "\uf1c5": ("png", "jpg", "jpeg", "gif", "bmp", "svg", "webp", "heic", "tiff"),
    "\uf1c6": ("zip", "tar", "gz", "tgz", "bz2", "xz", "7z", "rar", "dmg"),
    "\uf1c7": ("mp3", "wav", "flac", "m4a", "aac", "ogg"),
    "\uf1c8": ("mp4", "mkv", "mov", "avi", "webm", "m4v"),
    "\uf1c9": (
        "py", "js", "ts", "tsx", "jsx", "json", "yaml", "yml", "toml", "sh",
        "html", "css", "c", "h", "cpp", "rs", "go", "java", "rb", "lua", "sql",
    ),
    "\uf15c": ("txt", "md", "rst", "log", "org"),
}

# The way round the lookup is actually done. Written the other way above
# because a glyph with its kinds listed behind it can be read; a hundred
# extensions each with the same glyph after it cannot
_ICON_BY_SUFFIX = {
    suffix: icon for icon, suffixes in FILE_ICONS.items() for suffix in suffixes
}

FOLDER_ICON = "\uf07b"


def file_icon(name: str) -> str:
    """
    The glyph a file of this name is drawn with
    """

    suffix = Path(name).suffix.lstrip(".").lower()

    return _ICON_BY_SUFFIX.get(suffix, GENERIC_ICON)


class Opened(Enum):
    """
    How an attempt to open something went

    Opening a *file* has an outcome opening a URL does not: the address of a
    page is either taken or not taken, while a file can simply no longer be
    where the note says it is. That is a different thing to say and a
    different thing to offer to do about it, so it is a different answer.
    """

    OK = "ok"
    MISSING = "missing"
    NO_OPENER = "no-opener"


@dataclass(frozen=True)
class Opener:
    """
    One way of handing something to the desktop

    `windows_path` marks the openers that live on the other side of WSL: they
    are Windows programs, and a Linux path means nothing to them.
    """

    name: str
    arguments: Tuple[str, ...] = ()
    windows_path: bool = False


# Every opener there is, and `openers()` puts them in the order this machine
# should try them in.
#
# `rundll32.exe` is the URL handler itself rather than `explorer.exe`, which
# is the obvious way in and the wrong one: handed a URL with a query string on
# it, explorer gives up on the address and opens a File Explorer window
# instead. Handed a file it does the right thing, but there is no reason to
# keep two doors when one of them opens both
MAC_OPENER = Opener("open")
WSL_OPENERS = (Opener("wslview"), Opener("rundll32.exe", ("url.dll,FileProtocolHandler",), True))
LINUX_OPENER = Opener("xdg-open")


@lru_cache(maxsize=1)
def openers() -> Tuple[Opener, ...]:
    """
    The openers to try, best first for this machine

    All of them, every time, rather than only the one that belongs here: the
    ordering is what is really being decided, and a machine that has been set
    up unusually - `wslview` installed on a plain Linux box, say - then still
    finds something rather than looking dead.
    """

    if platform.system() == "Darwin":
        return (MAC_OPENER, LINUX_OPENER, *WSL_OPENERS)

    if is_wsl():
        return (*WSL_OPENERS, LINUX_OPENER, MAC_OPENER)

    return (LINUX_OPENER, *WSL_OPENERS, MAC_OPENER)


def spawn(argv: Sequence[str]) -> bool:
    """
    Run something and forget about it; False when it could not be started

    Detached, with all three streams tied off: whatever is spawned must not
    write into the terminal dooit is drawing in, and must not keep a handle on
    it either.
    """

    try:
        Popen(
            list(argv),
            stdin=DEVNULL,
            stdout=DEVNULL,
            stderr=DEVNULL,
            start_new_session=True,
        )
    except OSError:
        return False

    return True


def hand_over(target: str, path: Optional[Path] = None) -> bool:
    """
    Hand `target` to the first opener this machine has; False when it has none

    `path` is the file `target` names, when it names one: an opener that lives
    on the Windows side is handed the path written the Windows way, and every
    other one is handed exactly what it was given.
    """

    for opener in openers():
        command = which(opener.name)

        if command is None:
            continue

        argument = target

        if opener.windows_path and path is not None and is_wsl():
            argument = to_windows(path)

        if spawn([command, *opener.arguments, argument]):
            return True

    return False


def open_path(path: Path) -> Opened:
    """
    Open a file the way double-clicking it opens it

    Which application that is, is the desktop's business and not this one's:
    what is handed over is the path, and what comes back is only whether
    anybody took it.
    """

    if not path.exists():
        return Opened.MISSING

    return Opened.OK if hand_over(str(path), path) else Opened.NO_OPENER


def read_attachments(stored: str) -> List[Path]:
    """
    The files a note carries, as they are written down: one path per line

    Anything that no longer reads as a path is dropped rather than carried
    along as a line nobody can open - which is what a column edited by hand,
    or written by a version that kept something else in it, would leave.
    """

    found = []

    for line in stored.splitlines():
        path = resolve_path(line)

        if path is not None and path not in found:
            found.append(path)

    return found


def write_attachments(paths) -> str:
    """
    The other way round: the column as a list of files writes it
    """

    return "\n".join(str(path) for path in paths)


def display_name(target: str) -> str:
    """
    What a file link is called: the name of the file, and nothing else

    A path is mostly the answer to "where", and where is not what tells one
    attachment from another in a list of them.
    """

    path = resolve_path(target)

    if path is not None:
        return path.name or str(path)

    return target.rsplit("/", 1)[-1] or target
