"""
The one-way move of a database's notes to markdown

Notes used to be stored with bullet glyphs, a quote bar, a title over a rule and
zero-width emphasis marks. A database that hasn't been moved yet is copied aside,
then has every note rewritten. `PRAGMA user_version` is the marker that it's done.

The markup is written out here rather than shared with the note package, so
later changes to what a note draws can't change what this writes.
"""

import re
import shutil
from datetime import datetime
from pathlib import Path
from typing import List

from sqlalchemy.engine import Engine

MARKDOWN_NOTES_VERSION = 1

BACKUP_FOLDER = "backups"

# Every table with a `note` column. Bin rows are ordinary rows of `todo`.
NOTE_TABLES = ("todo", "pinnednote")

INDENT = "  "

MD_BULLET = "- "
MD_QUOTE = "> "
MD_HEADER = "# "
MD_RULE = "---"
MD_EMPH = "**"

EMPH_MARK = "\N{ZERO WIDTH SPACE}"
QUOTE_GLYPH = "▎ "
EMPH_RE = re.compile(rf"{EMPH_MARK}([^{EMPH_MARK}]+){EMPH_MARK}")
ITEM_RE = re.compile(r"^(?P<indent>[ \t]*)(?P<marker>[•◦▪] |(?P<number>\d+)\. )")
QUOTE_RE = re.compile(rf"^[ \t]*{QUOTE_GLYPH}")
RULE_RE = re.compile(r"^─{3,}[ \t]*$")


class BackupFailed(Exception):
    """The database couldn't be copied aside, so its notes were left alone."""


def _emphasis(line: str) -> str:
    """A line with its emphasis pairs written as markdown, orphan marks dropped."""

    def write(match: re.Match) -> str:
        phrase = match.group(1)
        words = phrase.strip()

        if not words:
            return phrase

        # Markdown won't open a pair against a space, so spaces go outside it
        lead = phrase[: len(phrase) - len(phrase.lstrip())]
        trail = phrase[len(phrase.rstrip()) :]

        return lead + MD_EMPH + words + MD_EMPH + trail

    return EMPH_RE.sub(write, line).replace(EMPH_MARK, "")


def to_markdown(text: str) -> str:
    """
    A note in the old format written as markdown: a title over its rule becomes
    a `#` heading, a rule alone `---`, bullets `- ` and the quote bar `> `.
    Nested items sit 2 spaces in per level, numbered ones included.
    """

    lines = text.split("\n")
    out: List[str] = []
    quoted = False
    row = 0

    while row < len(lines):
        line = lines[row]
        following = lines[row + 1] if row + 1 < len(lines) else ""

        if RULE_RE.match(line):
            out.append(MD_RULE)
            quoted = False
            row += 1
            continue

        if line.strip() and RULE_RE.match(following):
            out.append(MD_HEADER + _emphasis(line.strip()))
            quoted = False
            row += 2
            continue

        quote = QUOTE_RE.match(line)
        bar = line[: quote.end()].replace(QUOTE_GLYPH, MD_QUOTE) if quote else ""
        body = line[quote.end() :] if quote else line

        # A line straight after a quote would be read as more of it
        if quoted and not bar and line.strip():
            out.append("")

        quoted = bool(bar)

        item = ITEM_RE.match(body)

        if item:
            depth = len(item.group("indent").expandtabs(len(INDENT))) // len(INDENT)
            marker = MD_BULLET if item.group("number") is None else item.group("marker")

            body = INDENT * depth + marker + body[item.end() :]

        out.append(bar + _emphasis(body))
        row += 1

    return "\n".join(out)


def migration_due(engine: Engine) -> bool:
    with engine.connect() as connection:
        version = connection.exec_driver_sql("PRAGMA user_version").scalar()

    return (version or 0) < MARKDOWN_NOTES_VERSION


def back_up_database(path: Path) -> None:
    """Copy the database into `backups` beside it; raises `BackupFailed` if it can't."""

    stamp = datetime.now().strftime("%Y%m%d-%H%M%S")
    backup = path.parent / BACKUP_FOLDER / f"{path.stem}-before-markdown-{stamp}{path.suffix}"

    try:
        backup.parent.mkdir(parents=True, exist_ok=True)
        shutil.copy2(path, backup)
    except OSError as error:
        # A partial copy must not pass for a backup
        if backup.is_file():
            backup.unlink()

        raise BackupFailed(f"Could not back up {path} to {backup}: {error}") from error


def migrate_notes(engine: Engine) -> None:
    """Convert every note and set the marker, all or nothing."""

    with engine.begin() as connection:
        for table in NOTE_TABLES:
            rows = connection.exec_driver_sql(
                f"SELECT id, note FROM {table} WHERE note != ''"
            ).all()

            for id_, note in rows:
                converted = to_markdown(note)

                if converted != note:
                    connection.exec_driver_sql(
                        f"UPDATE {table} SET note = ? WHERE id = ?", (converted, id_)
                    )

        connection.exec_driver_sql(f"PRAGMA user_version = {MARKDOWN_NOTES_VERSION}")
