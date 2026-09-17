#!/usr/bin/env python3
"""
Regenerate the SVG screenshots the docs site embeds.

Runs todooit headlessly through Textual's own pilot -- no terminal, no window,
nothing on screen -- seeds one throwaway database with the same demo data every
time, walks to each feature and writes an SVG out of the rendered frame.

    uv run python site/scripts/screenshots.py

The database is a temporary file that is thrown away afterwards, and
``TODOOIT_HOME`` is pointed at a temporary directory before todooit is
imported, so nothing here can touch a real instance or load a user config.
"""

import asyncio
import os
import shutil
import sys
import tempfile
from datetime import datetime, timedelta
from pathlib import Path

REPO_ROOT = Path(__file__).resolve().parents[2]
OUT_DIR = REPO_ROOT / "site" / "docs" / "public" / "screenshots"

# The frame every screenshot is taken in. Wide enough for both panes plus all
# the todo columns, tall enough that a seeded project does not scroll.
TERMINAL_SIZE = (140, 34)

# Dooit.CSS_PATH is evaluated in the class body, so the cache directory is
# frozen at import time -- this has to happen before todooit is imported.
_INSTANCE = Path(tempfile.mkdtemp(prefix="todooit-shots-"))
os.environ["TODOOIT_HOME"] = str(_INSTANCE)

sys.path.insert(0, str(REPO_ROOT))

from textual.pilot import Pilot  # noqa: E402

from todooit.api import PinnedNote, Project, Todo, manager  # noqa: E402
from todooit.api.recycle import move_todo_to_bin  # noqa: E402
from todooit.ui.tui import Dooit  # noqa: E402
from todooit.ui.widgets.trees.fixed_todos_tree import FixedTodosTree  # noqa: E402


def _today(hour: int = 0, minute: int = 0) -> datetime:
    return datetime.now().replace(
        hour=hour, minute=minute, second=0, microsecond=0
    )


def seed() -> None:
    """
    The demo data every screenshot is taken against

    Written through the API rather than as SQL, so the hooks that keep a
    parent and its steps in step run exactly as they do in the app.
    """

    def project(name: str, color: int, parent: Project = None) -> Project:
        p = parent.add_project() if parent else Project()
        p.save()
        p.description = name
        p.save()
        p.set_color(color)
        return p

    def todo(
        parent,
        text: str,
        priority: int = 0,
        scheduled: datetime = None,
        due: datetime = None,
        agent: bool = False,
        recurrence: timedelta = None,
        note: str = "",
        done: bool = False,
    ) -> Todo:
        t = parent.add_todo()
        t.save()
        t.description = text
        t.priority = priority
        t.scheduled = scheduled
        t.due = due
        t.agent = agent
        t.recurrence = recurrence
        t.note = note
        t.save()

        if done:
            t.toggle_complete()
            t.save()

        return t

    work = project("Work", 1)          # blue
    home = project("Home", 2)          # green
    project("Reading", 6, parent=home)  # cyan, nested under Home

    todo(
        work,
        "Ship the docs site",
        priority=1,
        scheduled=_today(9),
        due=_today() + timedelta(days=2),
        note=NOTE_TEXT,
    )
    todo(work, "Review the migration PR", priority=2, scheduled=_today())
    todo(
        work,
        "Hand the flaky test to the agent",
        priority=3,
        scheduled=_today(),
        agent=True,
    )
    todo(work, "Write the release notes", due=_today() + timedelta(days=5))
    todo(work, "Archive last quarter's board", done=True)

    todo(
        home,
        "Water the plants",
        scheduled=_today(),
        recurrence=timedelta(weeks=1),
    )
    todo(home, "Call the dentist", priority=1, scheduled=_today() - timedelta(days=1))
    todo(home, "Book the train to Vienna", scheduled=_today() + timedelta(days=1))
    todo(home, "Pick up the parcel", scheduled=_today() + timedelta(days=3))

    binned = todo(home, "Renew the gym membership")
    move_todo_to_bin(binned)

    PinnedNote.set_text(PINNED_TEXT)
    manager.commit()


NOTE_TEXT = """\
# Docs site

- VitePress in site/
  - sidebar, local search, edit links
- screenshots come out of the pilot

> Deploys on every push to main

*Check the base path before the first deploy.*

See [the repo](https://github.com/gslama12/todooit) for the workflow.
"""

PINNED_TEXT = """\
# Scratchpad

- ask about the Q3 numbers
- *no task for this yet*

> The pinned note belongs to nothing, which is the point of it.
"""


async def boot(pilot: Pilot) -> Dooit:
    """Waits out the startup jump to the Today pane"""

    app = pilot.app

    for _ in range(40):
        await pilot.pause()

        switcher = app.screen.query_one("#todo_switcher")
        if isinstance(switcher.visible_content, FixedTodosTree):
            if app.focused is switcher.visible_content:
                return app

    raise AssertionError("The app never settled on the Today pane")


async def shot(app: Dooit, name: str) -> None:
    await asyncio.sleep(0.1)
    app.save_screenshot(filename=f"{name}.svg", path=str(OUT_DIR))
    print(f"  {name}.svg")


async def press(pilot: Pilot, *keys: str) -> None:
    await pilot.press(*keys)
    await pilot.pause()


# Every screenshot: a name, and the keys that get from the Today pane to it.
# Each one starts from a fresh boot, so a shot can never inherit the state the
# one before it left behind.
SCENES = (
    ("today", ()),
    ("upcoming", ("gu",)),
    ("completed", ("gc",)),
    ("bin", ("gb",)),
    # Two rows down the projects pane (past Today and Upcoming) onto Work,
    # then across into its tasks
    ("project", ("j", "l", "l", "ö")),
    ("help", ("?",)),
    ("quick-add", ("C", *"Call the dentist #Home p1 tomorrow 09:00")),
    ("search", ("/", *"call")),
    # Onto the first task in Work, then the move window
    ("move", ("j", "l", "l", "ö", "M")),
    # The note on the first task of Work, which is the seeded one
    ("note", ("j", "l", "l", "ö", " ")),
    ("pinned-note", ("m",)),
    # A date field, then the word that opens the month over it
    ("calendar", ("j", "l", "l", "ö", "s", *"cal")),
)


async def main() -> int:
    OUT_DIR.mkdir(parents=True, exist_ok=True)
    db_path = _INSTANCE / "screenshots.db"

    print(f"writing to {OUT_DIR}")

    for name, keys in SCENES:
        # A database per scene, seeded identically: the shots that type into
        # the app must not leave anything behind for the ones after them
        if db_path.exists():
            db_path.unlink()

        app = Dooit(db_path=str(db_path))
        seed()

        async with app.run_test(size=TERMINAL_SIZE) as pilot:
            await boot(pilot)

            if keys:
                await press(pilot, *keys)

            await shot(app, name)

    return 0


if __name__ == "__main__":
    try:
        raise SystemExit(asyncio.run(main()))
    finally:
        shutil.rmtree(_INSTANCE, ignore_errors=True)
