#!/usr/bin/env python3
"""
Regenerate the SVG screenshots the docs site and the README embed.

Runs todooit headlessly through Textual's own pilot -- no terminal, no window,
nothing on screen -- seeds one throwaway workspace, walks to each feature and
writes an SVG out of the rendered frame.

    uv run --with "fonttools[woff]" python site/scripts/screenshots.py

fonttools is asked for on the command line rather than added to the project:
it is what subsets the font below, and nothing the app or the test suite does
needs it.

Two things are done to the frame Textual hands back:

* Rich's SVG template points at Fira Code on a CDN, which an <img> is not
  allowed to fetch and which has no Nerd Font glyphs anyway -- so every icon
  todooit draws would come out as a blank box. The font is swapped for a
  subset of JetBrainsMono Nerd Font Mono, base64'd into each file, which keeps
  the SVG self-contained and renders the icons anywhere.
* The frame is square, which is what the docs pages are laid out for.

The database is a temporary file that is thrown away afterwards, and
``TODOOIT_HOME`` is pointed at a temporary directory before todooit is
imported, so nothing here can touch a real instance or load a user config.
"""

import asyncio
import base64
import io
import os
import re
import shutil
import sys
import tempfile
import xml.etree.ElementTree as ET
from datetime import datetime, timedelta
from pathlib import Path
from typing import Dict, Iterable, Optional, Sequence, Set, Tuple

REPO_ROOT = Path(__file__).resolve().parents[2]
OUT_DIR = REPO_ROOT / "site" / "docs" / "public" / "screenshots"

# The frame every screenshot is taken in.
#
# Rich draws a cell 12.02px wide and 24.4px tall and puts 50px of chrome above
# the terminal body, so a square image is `COLUMNS * 12.02 = ROWS * 24.4 + 50`.
# At 140 columns that lands on 69 rows, which is also a tall enough window that
# a seeded project is read without scrolling.
COLUMNS = 140
ROWS = 69

# The font the app is actually used in. The *Mono* cut of the Nerd Font is the
# one to subset: its icons are forced to one cell, at exactly the 0.6em advance
# Fira Code has, so the columns Rich positioned still line up once the font
# underneath them changes.
FONT_FAMILY = "JetBrainsMono Nerd Font Mono"
FONT_FILES = {
    "regular": "JetBrainsMonoNerdFontMono-Regular.ttf",
    "bold": "JetBrainsMonoNerdFontMono-Bold.ttf",
}

def font_dirs() -> Sequence[Path]:
    """Where a Nerd Font install puts its files. `--font-dir` adds one."""

    roots = [
        Path.home() / ".local/share/fonts",
        Path.home() / ".fonts",
        Path("/usr/share/fonts"),
        Path("/usr/local/share/fonts"),
        Path.home() / "Library/Fonts",
        Path("/Library/Fonts"),
        # WSL reaching the Windows font stores, which is where this was first
        # run. Named exactly rather than searched: a walk of a Windows profile
        # takes minutes over drvfs and would find the font last.
        Path("/mnt/c/Windows/Fonts"),
    ]

    windows_users = Path("/mnt/c/Users")
    if windows_users.exists():
        roots += [
            home / "AppData/Local/Microsoft/Windows/Fonts"
            for home in windows_users.iterdir()
            if home.is_dir()
        ]

    return roots

# Todooit.CSS_PATH is evaluated in the class body, so the cache directory is
# frozen at import time -- this has to happen before todooit is imported.
_INSTANCE = Path(tempfile.mkdtemp(prefix="todooit-shots-"))
os.environ["TODOOIT_HOME"] = str(_INSTANCE)

sys.path.insert(0, str(REPO_ROOT))

from textual.pilot import Pilot  # noqa: E402

from todooit.api import Project, Todo, manager  # noqa: E402
from todooit.api.cadence import Cadence  # noqa: E402
from todooit.api.recycle import move_todo_to_bin  # noqa: E402
from todooit.ui.tui import Todooit  # noqa: E402
from todooit.ui.widgets.trees.fixed_todos_tree import FixedTodosTree  # noqa: E402
from todooit.utils.files import write_attachments  # noqa: E402

# --------------------------------------------------------------------------
# The workspace every screenshot is taken against
# --------------------------------------------------------------------------


def at(hour: int = 0, minute: int = 0, days: int = 0) -> datetime:
    """A time today, or `days` either side of it"""

    base = datetime.now().replace(hour=hour, minute=minute, second=0, microsecond=0)
    return base + timedelta(days=days)


# A note's markup is drawn as it is *typed* -- `- ` becomes a bullet, `---` a
# rule, `*stars*` a pair of zero-width marks -- so a note written straight into
# the database comes up as the raw characters and shows none of it. The two
# notes below are therefore typed through the pilot, one key at a time, exactly
# as a person would write them.
# A note opens in NORMAL, so `i` comes first; it ends back in NORMAL, off the
# last line, since the cursor's own line is drawn as the raw markdown.
NOTE_KEYS = (
    "i",
    *"# Release checklist", "enter",
    *"- Tag the release", "enter",
    "tab", *"Changelog from the commit log", "enter",
    *"Check the migration notes", "enter",
    "shift+tab", *"Build the docs site", "enter",
    *"Announce it", "enter",
    # An empty item is where a list ends
    "enter", "enter",
    *"> Nothing ships on a friday.", "enter",
    "enter",
    # Three dashes on a line of their own become the rule
    *"---", "enter",
    *"*Ask about the database backup first.*", "enter",
    "enter",
    # The link last on its line: a markdown one is drawn under its name with
    # the address folded away behind it, and the underline is the name's
    *"For the rest, see [the release runbook](https://github.com/gslama12/todooit)",
    "escape", "k",
)

PINNED_KEYS = (
    "i",
    *"# Scratchpad", "enter",
    *"- Ask about the Q3 numbers", "enter",
    *"The invoice template moved", "enter",
    *"*No task for any of this yet*", "enter",
    "enter", "enter",
    *"> The pinned note belongs to nothing, which is the point of it.", "enter",
    "escape",
)

# Plain text, only so the Note column has something to mark those rows with
SHORT_NOTE = "Ask about the database backup first."


def seed() -> Dict[str, Project]:
    """
    A believable workspace, written through the API rather than as SQL so the
    hooks that keep a parent and its steps in step run as they do in the app
    """

    projects: Dict[str, Project] = {}

    def project(name: str, color: int, parent: Optional[Project] = None) -> Project:
        p = parent.add_project() if parent else Project()
        p.save()
        p.description = name
        p.save()
        p.set_color(color)
        projects[name] = p
        return p

    def todo(
        parent,
        text: str,
        priority: int = 0,
        scheduled: Optional[datetime] = None,
        due: Optional[datetime] = None,
        # A timedelta, or the text typed into the field (`eom`)
        recurrence=None,
        note: str = "",
        done: bool = False,
        attachments: Sequence[str] = (),
    ) -> Todo:
        t = parent.add_todo()
        t.save()
        t.description = text
        t.priority = priority
        t.scheduled = scheduled
        t.due = due
        if isinstance(recurrence, timedelta):
            recurrence = Cadence.from_timedelta(recurrence)
        elif isinstance(recurrence, str):
            recurrence = Cadence.parse(recurrence)
        t.recurrence = recurrence
        t.note = note
        if attachments:
            t.attachments = write_attachments([Path(a) for a in attachments])
        t.save()

        if done:
            t.toggle_complete()
            t.save()

        return t

    # c0 red, c1 blue, c2 green, c3 yellow, c4 orange, c5 purple, c6 cyan,
    # c8 brown. Enough projects that the pane is a tree rather than a list.
    work = project("Work", 1)
    platform = project("Platform", 6, parent=work)
    home = project("Home", 2)
    reading = project("Reading", 6, parent=home)
    house = project("House", 4, parent=home)
    side = project("Side project", 5)
    health = project("Health", 0)
    learning = project("Learning", 3)
    someday = project("Someday", 8)

    # --- Work -------------------------------------------------------------
    release = todo(
        work,
        "Ship the 1.1 release",
        priority=1,
        scheduled=at(9),
        due=at(days=2),
    )
    todo(release, "Write the changelog", priority=2, scheduled=at(9))
    todo(release, "Tag and build", priority=3, due=at(days=2))
    todo(release, "Draft the announcement")
    todo(release, "Update the install docs", scheduled=at(days=1))

    todo(work, "Review the migration PR", priority=2, scheduled=at(11))
    todo(
        work,
        "Fix the flaky pilot test",
        priority=3,
        scheduled=at(),
    )
    todo(work, "Team standup", scheduled=at(9, 30), recurrence=timedelta(days=1))
    todo(work, "Expenses for August", scheduled=at(days=-2), priority=2)
    todo(
        work,
        "Quarterly report",
        due=at(days=6),
        note=SHORT_NOTE,
        # Only the paths are kept, so they needn't exist for the strip to draw
        attachments=(
            "/home/me/reports/q3-figures.xlsx",
            "/home/me/reports/q3-draft.docx",
            "/home/me/reports/board-feedback.pdf",
        ),
    )
    todo(work, "Book the offsite room", scheduled=at(days=3))
    todo(work, "Interview debrief", priority=2, scheduled=at(days=1), due=at(days=1))
    todo(work, "Renew the TLS certificate", priority=1, due=at(days=5))
    todo(work, "Write up the incident", due=at(days=4))
    todo(work, "Plan the Q4 roadmap", scheduled=at(days=7))
    todo(work, "One-to-ones", scheduled=at(14), recurrence=timedelta(weeks=2))
    todo(work, "Clear the inbox", recurrence=timedelta(days=1))
    todo(work, "Chase the vendor contract", priority=2, due=at(days=10))
    todo(work, "Review the on-call rota", scheduled=at(days=8))
    todo(work, "Update the runbook index")
    todo(work, "Sign off the design review", priority=3, due=at(days=11))
    todo(work, "Prep the board slides", scheduled=at(days=9), due=at(days=13))
    todo(work, "Close the old support tickets", priority=3)
    todo(work, "Refresh the team wiki", scheduled=at(days=12))
    todo(work, "Budget forecast for Q4", due=at(days=15), note=SHORT_NOTE)
    todo(work, "Schedule the retro", scheduled=at(days=6))
    todo(work, "Tidy the shared drive")
    todo(work, "Archive last quarter board", done=True)
    todo(work, "Close the Q2 retro actions", done=True)
    todo(work, "Hand over the on-call pager", done=True)

    # --- Platform, under Work --------------------------------------------
    todo(platform, "Upgrade the runners", priority=2, scheduled=at(days=2))
    todo(platform, "Rotate the deploy keys", priority=1, due=at(days=3))
    todo(platform, "Cache the test fixtures", scheduled=at(days=5))
    todo(platform, "Drop the old staging box", note=SHORT_NOTE)

    # --- Home -------------------------------------------------------------
    groceries = todo(home, "Groceries", scheduled=at(17))
    todo(groceries, "Coffee")
    todo(groceries, "Bread and cheese")
    todo(groceries, "Something for the weekend")

    weekend = todo(home, "Weekend in the mountains", scheduled=at(days=2))
    todo(weekend, "Book the hut", priority=1, due=at(days=1))
    todo(weekend, "Check the forecast")
    todo(weekend, "Pack the boots")

    todo(home, "Water the plants", scheduled=at(), recurrence=timedelta(weeks=1))
    todo(home, "Pay the rent", recurrence="eom")
    todo(home, "Call the dentist", priority=1, scheduled=at(days=-1))
    todo(home, "Book the train to Vienna", scheduled=at(days=1), due=at(days=4))
    todo(home, "Pick up the parcel", scheduled=at(days=3))
    todo(home, "Fix the kitchen tap", priority=3)
    todo(home, "Send the birthday card", priority=2, due=at(days=2))
    todo(home, "Bins out", scheduled=at(19), recurrence=timedelta(weeks=1))
    todo(home, "Book the car service", priority=2, due=at(days=9))
    todo(home, "Reply to the landlord", priority=1, due=at(days=1))
    todo(home, "Cancel the old phone plan", scheduled=at(days=5))
    todo(home, "Print the tax receipts", priority=3, due=at(days=14))
    todo(home, "Sort the photo backlog")
    todo(home, "Ring the grandparents", scheduled=at(18), recurrence=timedelta(weeks=1))
    todo(home, "Find a plumber", priority=2)
    todo(home, "Renew the car insurance", done=True)
    todo(home, "Return the library books", done=True)

    # --- Reading and House, under Home -----------------------------------
    todo(reading, "Designing Data-Intensive Applications", priority=2)
    todo(reading, "The Rust book, chapter 13", scheduled=at(days=2))
    todo(reading, "https://textual.textualize.io/guide/", priority=3)
    todo(reading, "Finish the Le Guin", scheduled=at(days=6))

    todo(house, "Bleed the radiators", priority=2, due=at(days=8))
    todo(house, "Order the firewood", scheduled=at(days=4))
    todo(house, "Service the boiler", recurrence=timedelta(weeks=26))

    # --- Side project -----------------------------------------------------
    todo(side, "Sketch the landing page", priority=2, scheduled=at(days=1))
    todo(side, "Pick a database", priority=1, due=at(days=9))
    todo(side, "Buy the domain", scheduled=at(days=4))
    todo(side, "Read up on Pages deploys")
    todo(side, "Write the README", scheduled=at(days=5))

    # --- Health -----------------------------------------------------------
    todo(health, "Swim", scheduled=at(7), recurrence=timedelta(days=3))
    todo(health, "Book the annual check-up", priority=2, due=at(days=12))
    todo(health, "Order new running shoes", scheduled=at(days=3))
    todo(health, "Physio exercises", recurrence=timedelta(days=1), done=True)

    # --- Learning ---------------------------------------------------------
    todo(learning, "Textual: reactive attributes", scheduled=at(days=1))
    todo(learning, "SQLAlchemy 2.0 typing", priority=3)
    todo(learning, "Finish the German B2 unit", recurrence=timedelta(days=2))

    # --- Someday ----------------------------------------------------------
    todo(someday, "Learn to sail")
    todo(someday, "Repaint the hallway")
    todo(someday, "Write the sourdough post")

    # --- and a few things thrown away ------------------------------------
    for text in (
        "Renew the gym membership",
        "Reply to the recruiter",
        "Chase the invoice again",
    ):
        move_todo_to_bin(todo(home, text))

    manager.commit()

    return projects


# --------------------------------------------------------------------------
# Driving the app
# --------------------------------------------------------------------------


async def boot(pilot: Pilot) -> Todooit:
    """Waits out the startup jump to the Today pane"""

    app = pilot.app

    for _ in range(60):
        await pilot.pause()

        switcher = app.screen.query_one("#todo_switcher")
        if (
            isinstance(switcher.visible_content, FixedTodosTree)
            and app.focused is switcher.visible_content
        ):
            return app

    raise AssertionError("The app never settled on the Today pane")


async def reveal(pilot: Pilot, project: Project) -> None:
    """Brings a project's own tasks pane to the front, as the cursor would"""

    pilot.app.api.vars.projects_tree.highlight_id(project.uuid)
    await pilot.pause()


# Every screenshot: a name, the project to stand in (None for wherever the app
# opens, which is Today), and the keys that get from there to what is wanted.
# Each one starts from a fresh boot against a freshly seeded database, so a
# shot can never inherit the state the one before it left behind.
#
# A chord is written out one key at a time -- ("g", "u"), never ("gu") -- since
# the pilot presses a *key* and there is no key called "gu". The key manager
# holds the halves until they match, so two presses are one chord.
def find(text: str) -> Tuple[str, ...]:
    """The finder walking the cursor over to a task, wherever it is filed"""

    return ("/", *text, "enter")


SCENES: Sequence[Tuple[str, Optional[str], Sequence[str]]] = (
    # --- the workspace, for the README and the docs home ------------------
    ("workspace", "Work", ("ö",)),
    # --- the four fixed projects ------------------------------------------
    ("today", None, ()),
    ("upcoming", None, ("g", "u")),
    ("completed", None, ("g", "c")),
    ("bin", None, ("g", "b")),
    # --- projects and tasks -----------------------------------------------
    ("nested-projects", "Reading", ()),
    ("child-tasks", "Home", ("ö",)),
    ("sort", "Work", ("ö", "S", "D")),
    ("confirm", "Home", ("ö", "y", "y")),
    # --- the overlays ------------------------------------------------------
    ("quick-add", None, ("C", *"Call the dentist #Home p1 tomorrow 09:00")),
    ("search", None, ("/", *"boo")),
    ("move", "Work", ("ö", "M", *"Sid")),
    ("note", None, (*find("Ship the 1.1"), " ", *NOTE_KEYS)),
    ("pinned-note", None, ("m", *PINNED_KEYS)),
    ("calendar", "Work", ("ö", "s", *"cal")),
    ("help", None, ("?",)),
    # --- added with the vim work ------------------------------------------
    # Flash: a label on every row on screen, typing one jumps there
    ("flash", "Work", ("ö", "f")),
    # A description edited with vim's keys: `e` lands in NORMAL, `cw` changes
    # the word under the cursor
    ("vim-description", "Work", ("ö", "e", "b", "c", "w", *"2.0")),
    # Every key a note knows, with `space ?`
    ("note-help", None, (*find("Ship the 1.1"), " ", *NOTE_KEYS, "space", "question_mark")),
    # The finder looking in notes: a `>` first
    ("search-notes", None, ("/", *">backup")),
    # Files attached to a note, in the strip along its bottom
    ("attachments", None, (*find("Quarterly report"), " ", "g", "f")),
)


async def capture() -> None:
    OUT_DIR.mkdir(parents=True, exist_ok=True)
    db_path = _INSTANCE / "screenshots.db"

    for name, project_name, keys in SCENES:
        if db_path.exists():
            db_path.unlink()

        app = Todooit(db_path=str(db_path))
        projects = seed()

        async with app.run_test(size=(COLUMNS, ROWS)) as pilot:
            await boot(pilot)

            # The name Rich writes into the frame's chrome
            app.title = "todooit"

            if project_name:
                await reveal(pilot, projects[project_name])

            if keys:
                await pilot.press(*keys)
                await pilot.pause()

            await asyncio.sleep(0.1)
            app.save_screenshot(filename=f"{name}.svg", path=str(OUT_DIR))
            print(f"  {name}.svg")


# --------------------------------------------------------------------------
# Putting the real font into the frames
# --------------------------------------------------------------------------


# Rich writes two of these, both pointing at Fira Code on a CDN
FONT_FACE_RE = re.compile(r"@font-face\s*\{[^}]*\}\s*")
MATRIX_FAMILY_RE = re.compile(r"font-family:\s*Fira Code,\s*monospace;")


def find_font(name: str, extra: Optional[Path]) -> Path:
    roots = [extra, *font_dirs()] if extra else list(font_dirs())

    for root in roots:
        # Another Windows user's profile can't be looked into
        try:
            if not root or not root.exists():
                continue

            # Windows keeps per-user installs several levels down, so this
            # looks rather than insisting on one layout
            for candidate in root.rglob(name):
                return candidate
        except PermissionError:
            continue

    raise SystemExit(
        "Could not find {}.\n"
        "Install JetBrainsMono Nerd Font, or pass --font-dir <path>.\n"
        "Without it every icon in the screenshots comes out as a blank box."
        .format(name)
    )


def characters_used(paths: Iterable[Path]) -> Set[str]:
    """Every character the frames actually draw"""

    used: Set[str] = set()

    for path in paths:
        for element in ET.parse(path).getroot().iter():
            if element.tag.rsplit("}", 1)[-1] == "text":
                used.update(element.text or "")

    # The blanks Rich pads rows out with, whatever the frames happened to hold
    used.update("  ")
    return used


def subset_woff2(font_path: Path, characters: Set[str]) -> bytes:
    from fontTools import subset
    from fontTools.ttLib import TTFont

    font = TTFont(font_path)

    options = subset.Options()
    # Ligatures would merge two cells into one glyph and take the row's columns
    # with them, so the layout tables go entirely
    options.layout_features = []
    options.notdef_outline = True

    subsetter = subset.Subsetter(options=options)
    subsetter.populate(unicodes={ord(character) for character in characters})
    subsetter.subset(font)

    font.flavor = "woff2"
    buffer = io.BytesIO()
    font.save(buffer)
    return buffer.getvalue()


def font_face_css(regular: bytes, bold: bytes) -> str:
    def face(data: bytes, weight: int) -> str:
        encoded = base64.b64encode(data).decode("ascii")
        return (
            "    @font-face {\n"
            f'        font-family: "{FONT_FAMILY}";\n'
            f'        src: url("data:font/woff2;base64,{encoded}") format("woff2");\n'
            "        font-style: normal;\n"
            f"        font-weight: {weight};\n"
            "    }\n"
        )

    return face(regular, 400) + face(bold, 700)


def embed_font(paths: Sequence[Path], font_dir: Optional[Path]) -> None:
    characters = characters_used(paths)
    print(f"embedding {FONT_FAMILY} ({len(characters)} glyphs)")

    faces = font_face_css(
        subset_woff2(find_font(FONT_FILES["regular"], font_dir), characters),
        subset_woff2(find_font(FONT_FILES["bold"], font_dir), characters),
    )

    replacement = (
        f'font-family: "{FONT_FAMILY}", monospace;\n'
        "        font-variant-ligatures: none;"
    )

    for path in paths:
        svg = path.read_text(encoding="utf-8")
        svg = FONT_FACE_RE.sub("", svg)
        svg = svg.replace("<style>\n", "<style>\n" + faces, 1)
        svg = MATRIX_FAMILY_RE.sub(replacement, svg)
        path.write_text(svg, encoding="utf-8", newline="\n")


# --------------------------------------------------------------------------


async def main(font_dir: Optional[Path]) -> int:
    print(f"writing to {OUT_DIR}")
    await capture()

    embed_font([OUT_DIR / f"{name}.svg" for name, _, _ in SCENES], font_dir)
    return 0


if __name__ == "__main__":
    argv = sys.argv[1:]
    directory = None

    if "--font-dir" in argv:
        directory = Path(argv[argv.index("--font-dir") + 1]).expanduser()

    try:
        raise SystemExit(asyncio.run(main(directory)))
    finally:
        shutil.rmtree(_INSTANCE, ignore_errors=True)
