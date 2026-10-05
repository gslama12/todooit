"""Finder: searches every task in the DB, regardless of which pane is open, and
hands back the one picked (`MainScreen.reveal_todo` navigates to it).

A query starting with `>` searches notes instead of descriptions; the match
also carries the note line it was found on, so the note can open there.
"""

import re
from datetime import datetime
from itertools import groupby
from typing import Dict, Iterable, List, NamedTuple, Optional, Sequence, Tuple

from rich.cells import cell_len
from rich.console import Group, RenderableType
from rich.style import Style
from rich.table import Table
from rich.text import Text
from sqlalchemy import select

from todooit.api import BIN, COMPLETED, Todo, manager
from todooit.api.fixed_projects import project_path
from todooit.api.placement import home_of, project_of
from todooit.ui.widgets.trees.model_tree import GroupHeading
from todooit.utils import blend, day_label
from todooit.utils.links import drawn_column, fold_links

from .panel import DATE_ICON, FADE, PROJECT_ICON, PanelScreen

# Panel border title, as with quick-add
PANEL_TITLE = "Find task"
NOTES_TITLE = "Find in notes"

# Prefix that switches the search to notes instead of descriptions; only
# meaningful at the very start of the query
NOTE_PREFIX = ">"

# The checkbox the tasks pane draws its rows with, empty and ticked
CHECKBOX_EMPTY = "󰄱"
CHECKBOX_TICKED = "󰄵"

# Matches on screen at once; the border shows position within the full list
MAX_ROWS = 10

# Note matches take two lines (task + note line), so fewer fit than MAX_ROWS
MAX_NOTE_ROWS = 5

# How much of a note line to keep before a match that has to be cut, to read
# the word in context
SNIPPET_LEAD = 24

# How far a note's matched line is stepped in under its task
SNIPPET_INDENT = "  "

# Fade for a task no longer being worked on, matching the projects pane
MUTED_FADE = 0.55

# Counter shown in the bottom border
POSITION = "{} of {}"

HINT = "↑↓  move      enter  go to task      esc  cancel"
NOTES_HINT = "↑↓  move      enter  open note      esc  cancel"

EMPTY_QUERY = f"Type to find a task, {NOTE_PREFIX} for notes"
NO_MATCHES = "No task matches"
EMPTY_NOTE_QUERY = "Type to find in notes"
NO_NOTE_MATCHES = "No note matches"

# Markup a note line opens with (bullet, numbered item, quote, heading) --
# stripped here since the note itself draws these as glyphs
LINE_MARKER = re.compile(r"^\s*(?:(?:[-*+]|\d+[.)]|>+|#+)\s+)*")

# Draw order of match blocks: pending tasks first and unheaded (what the
# finder is for), then completed/binned, each headed by its pane's name
LIVE, DONE, BINNED = 0, 1, 2

SECTION_LABELS = {DONE: COMPLETED.title, BINNED: BIN.title}


def section_of(todo: Todo) -> int:
    """Which block a todo is drawn in: the one matching its home (see placement)."""

    home = home_of(todo)

    if home is BIN:
        return BINNED

    if home is COMPLETED:
        return DONE

    return LIVE


class NoteHit(NamedTuple):
    """Where in a note the query was found: row/column as the note itself counts
    them, column being where the first typed word starts.
    """

    row: int
    column: int
    line: str


class Candidate(NamedTuple):
    """A task with everything matched against precomputed once (built when the
    finder opens, read on every keystroke).
    """

    todo: Todo
    project: str
    haystack: str
    section: int
    # Filled in on the matches of a search through the notes, and only there
    hit: Optional[NoteHit] = None


class Found(NamedTuple):
    """What the finder hands back: the picked task, plus a note location if found there."""

    todo: Todo
    hit: Optional[NoteHit] = None


def note_query(query: str) -> Optional[str]:
    """The note search term, or None if the query isn't a note search."""

    if not query.startswith(NOTE_PREFIX):
        return None

    return query[len(NOTE_PREFIX) :]


def load_notes() -> Dict[int, str]:
    """Every non-empty note, by the id of its task.

    One query for all of them: `candidates()` builds its pool without notes,
    which are loaded separately for the ">" search.
    """

    query = select(Todo.id, Todo.note).where(Todo.note != "")

    return {id_: note for id_, note in manager.session.execute(query).all()}


class Match(NamedTuple):
    candidate: Candidate
    # What the matches are ordered by; see `rank` below
    order: tuple


def candidates() -> List[Candidate]:
    result = []

    for todo in Todo.all():
        project = project_of(todo)
        path = project_path(project) if project else ""
        result.append(
            Candidate(
                todo=todo,
                project=path,
                haystack=f"{todo.description}\n{path}".lower(),
                section=section_of(todo),
            )
        )

    return result


def _due_key(todo: Todo) -> tuple:
    """Sort key: dated tasks by deadline, undated ones after."""

    if todo.due is None:
        return (1, datetime.max)

    return (0, todo.due)


def rank(candidate: Candidate, terms: Sequence[str]) -> Optional[tuple]:
    """How well a task answers the query (sort key), or None if it doesn't match.

    Every term must appear in the description or project path, so a task can
    be found by location too (e.g. "api tests"). Ordered by section (pending
    first), then by how the first term matched (starts description > starts a
    word > substring > project-only), then by nearest deadline.
    """

    if not all(term in candidate.haystack for term in terms):
        return None

    description = candidate.todo.description.lower()
    lead = terms[0]

    if description.startswith(lead):
        position = 0
    elif any(word.startswith(lead) for word in description.split()):
        position = 1
    elif lead in description:
        position = 2
    else:
        position = 3

    return (candidate.section, position, _due_key(candidate.todo), description)


def rank_note(
    candidate: Candidate, note: str, terms: Sequence[str]
) -> Optional[Tuple[tuple, NoteHit]]:
    """Like `rank`, but matching against the note instead of the description.

    Returns the sort key plus the first line containing the first term (used
    as the hit location; later terms may be elsewhere in the note).
    """

    lower = note.lower()

    if not all(term in lower for term in terms):
        return None

    lead = terms[0]
    lines = note.split("\n")
    hit = None

    for row, line in enumerate(lines):
        column = line.lower().find(lead)

        if column != -1:
            hit = NoteHit(row, column, line)
            break

    if hit is None:  # pragma: no cover - the lead is in the note, so on a line
        return None

    words = re.findall(r"\w[\w'-]*|\S", lower)
    position = 0 if any(word.startswith(lead) for word in words) else 1

    description = candidate.todo.description.lower()
    order = (candidate.section, position, _due_key(candidate.todo), description)

    return order, hit


def search_notes(
    pool: Sequence[Candidate], notes: Dict[int, str], query: str
) -> List[Candidate]:
    """Tasks whose notes answer the query, best first, each with its matched line."""

    terms = query.lower().split()

    if not terms:
        return []

    matches = []

    for candidate in pool:
        note = notes.get(candidate.todo.id)

        if not note:
            continue

        ranked = rank_note(candidate, note, terms)

        if ranked is not None:
            order, hit = ranked
            matches.append(Match(candidate._replace(hit=hit), order))

    matches.sort(key=lambda match: match.order)
    return [match.candidate for match in matches]


def snippet(line: str, column: int, lead: int = SNIPPET_LEAD) -> str:
    """A note line as shown under its task: leading markup dropped, links folded
    to their names, and cut in front of a match too far along to fit.
    """

    marker = LINE_MARKER.match(line)
    skipped = marker.end() if marker else 0

    text = line[skipped:]
    column = max(0, column - skipped)

    # Folding shortens what comes before the match, so the column is carried
    # across the way the note carries its cursor
    folded, _ = fold_links(text)
    column = drawn_column(text, column)

    if column > lead:
        folded = "…" + folded[column - lead :].lstrip()

    return folded


def picked_out(text: Text, terms: Sequence[str], style: Style) -> Text:
    """Highlight every occurrence of each term, not just a leading match."""

    lower = text.plain.lower()

    for term in terms:
        start = lower.find(term)

        while start != -1:
            text.stylize(style, start, start + len(term))
            start = lower.find(term, start + len(term))

    return text


def search(pool: Sequence[Candidate], query: str) -> List[Candidate]:
    """The tasks that answer the query, best first."""

    terms = query.lower().split()

    if not terms:
        return []

    matches = []

    for candidate in pool:
        order = rank(candidate, terms)

        if order is not None:
            matches.append(Match(candidate, order))

    matches.sort(key=lambda match: match.order)
    return [match.candidate for match in matches]


class SearchScreen(PanelScreen):
    PANEL_TITLE = PANEL_TITLE
    HINT = HINT

    def __init__(self) -> None:
        super().__init__()

        self._pool: List[Candidate] = []
        self._matches: List[Candidate] = []

        # Fetched on the first note query, kept while the finder is open
        self._notes: Optional[Dict[int, str]] = None

        # The cursor, as an index into all matches; reset on every keystroke
        self._index = 0

        # The first match on screen
        self._offset = 0

    def _opened(self) -> None:
        self._pool = candidates()

    @property
    def in_notes(self) -> bool:
        """Whether what is typed is being looked for in the notes"""

        return note_query(self._input.value) is not None

    @property
    def rows(self) -> int:
        """How many matches are on screen at once"""

        return MAX_NOTE_ROWS if self.in_notes else MAX_ROWS

    @property
    def terms(self) -> List[str]:
        """The words typed, without the notes prefix"""

        query = note_query(self._input.value)

        if query is None:
            query = self._input.value

        return query.lower().split()

    # ------------------------------------------------------------------
    # Typing
    # ------------------------------------------------------------------

    def line_key(self, key: str) -> None:
        if key == "escape":
            self.dismiss(None)
            return

        if key == "enter":
            self.dismiss(self.selected)
            return

        if key in ("down", "ctrl+n"):
            self._move(1)
            return

        if key in ("up", "ctrl+p"):
            self._move(-1)
            return

        self._input.keypress(key)
        self._research()

    @property
    def selected(self) -> Optional[Found]:
        if not self._matches:
            return None

        candidate = self._matches[self._index]

        return Found(candidate.todo, candidate.hit)

    def _move(self, step: int) -> None:
        """Moves the cursor, wrapping at either end, and scrolls to keep it on screen"""

        if not self._matches:
            return

        self._index = (self._index + step) % len(self._matches)

        if self._index < self._offset:
            self._offset = self._index
        elif self._index >= self._offset + self.rows:
            self._offset = self._index - self.rows + 1

        self._redraw()

    def _research(self) -> None:
        query = note_query(self._input.value)

        if query is None:
            self._matches = search(self._pool, self._input.value)
        else:
            if self._notes is None:
                self._notes = load_notes()

            self._matches = search_notes(self._pool, self._notes, query)

        self._index = 0
        self._offset = 0
        self._redraw()

    # ------------------------------------------------------------------
    # Drawing
    # ------------------------------------------------------------------

    def _redraw(self) -> None:
        in_notes = self.in_notes

        self.panel.border_title = NOTES_TITLE if in_notes else PANEL_TITLE
        self.hint.update(NOTES_HINT if in_notes else HINT)
        self.panel.update(Group(self._line(), Text(), self._results()))

        # Shows position in the full list, since the window rarely shows all of it
        self.panel.border_subtitle = (
            POSITION.format(self._index + 1, len(self._matches))
            if self._matches
            else ""
        )

    def _results(self) -> RenderableType:
        in_notes = self.in_notes
        terms = self.terms

        if not terms:
            return self._faded(EMPTY_NOTE_QUERY if in_notes else EMPTY_QUERY)

        if not self._matches:
            return self._faded(NO_NOTE_MATCHES if in_notes else NO_MATCHES)

        window = list(
            enumerate(
                self._matches[self._offset : self._offset + self.rows],
                start=self._offset,
            )
        )
        widths = self._column_widths(candidate for _, candidate in window)

        blocks: List[RenderableType] = []

        # Grouped, not sliced by section: the visible window can straddle the
        # end of one block and the start of the next
        for section, rows in groupby(window, key=lambda row: row[1].section):
            if section != LIVE:
                blocks.append(self._heading(section, space_above=bool(blocks)))

            blocks.append(self._table(list(rows), terms, widths))

        return Group(*blocks)

    def _heading(self, section: int, space_above: bool) -> GroupHeading:
        """Block heading, matching the one the tasks pane uses for its own sections."""

        theme = self.theme

        return GroupHeading(
            label=SECTION_LABELS[section],
            label_style=self._faded_color(),
            rule_style=theme.background3,
            space_above=space_above,
        )

    def _column_widths(self, window: Iterable[Candidate]) -> Tuple[int, int]:
        """Deadline/project column widths, fixed across all blocks so columns don't
        shift sideways at each heading.
        """

        due = 0
        project = 0

        for candidate in window:
            due = max(due, cell_len(self._due(candidate.todo).plain))
            project = max(project, cell_len(self._project(candidate).plain))

        return due, project

    def _table(
        self,
        rows: List[Tuple[int, Candidate]],
        terms: Sequence[str],
        widths: Tuple[int, int],
    ) -> Table:
        # Expanded to the panel width (not just the longest row) so the project
        # column lines up and the cursor highlight is a full band
        table = Table.grid(expand=True, padding=(0, 1))
        table.add_column(width=1)
        table.add_column(ratio=1, no_wrap=True, overflow="ellipsis")
        table.add_column(justify="right", no_wrap=True, width=widths[0])
        table.add_column(justify="right", no_wrap=True, width=widths[1])

        for index, candidate in rows:
            style = self._row_style(index)

            table.add_row(
                self._status(candidate),
                # No highlight when found via note: the terms aren't in the title
                self._description(candidate, [] if candidate.hit else terms),
                self._due(candidate.todo),
                self._project(candidate),
                style=style,
            )

            if candidate.hit is not None:
                table.add_row(
                    Text(), self._snippet(candidate, terms), Text(), Text(), style=style
                )

        return table

    def _row_style(self, index: int) -> Style:
        if index != self._index:
            return Style()

        return Style(bgcolor=self.theme.background3)

    def _muted(self, color: str) -> str:
        """Fade a color the way a task no longer being worked on is drawn."""

        return blend(color, self.theme.background2, MUTED_FADE)

    def _status(self, candidate: Candidate) -> Text:
        """Checkbox in the priority color the pane gives it, or gray once done with."""

        theme = self.theme
        todo = candidate.todo
        colors = {1: theme.red, 2: theme.yellow, 3: theme.cyan}
        color = colors.get(
            todo.priority, blend(theme.foreground1, theme.background2, 0.5)
        )

        if candidate.section != LIVE:
            color = self._muted(theme.foreground1)
        elif todo.is_completed:
            color = blend(color, theme.background2, 0.35)

        return Text(
            CHECKBOX_TICKED if todo.is_completed else CHECKBOX_EMPTY,
            style=Style(color=color, bold=True),
        )

    def _description(self, candidate: Candidate, terms: Sequence[str]) -> Text:
        """Task description with every matched term highlighted, not just a leading one."""

        theme = self.theme
        live = candidate.section == LIVE
        color = theme.foreground2 if live else self._muted(theme.foreground1)
        accent = theme.primary if live else self._muted(theme.primary)

        text = Text(candidate.todo.description, style=Style(color=color))

        return picked_out(text, terms, Style(color=accent, bold=True))

    def _snippet(self, candidate: Candidate, terms: Sequence[str]) -> Text:
        """The note line the task was matched on, drawn dimmer than the row above it."""

        hit = candidate.hit
        assert hit is not None

        theme = self.theme
        live = candidate.section == LIVE
        color = self._faded_color()
        accent = theme.primary if live else self._muted(theme.primary)

        if not live:
            color = self._muted(theme.foreground1)

        text = Text(snippet(hit.line, hit.column), style=Style(color=color))
        text = picked_out(text, terms, Style(color=accent, bold=True))

        # Indented so it reads as belonging under the task's title
        return Text(SNIPPET_INDENT) + text

    def _due(self, todo: Todo) -> Text:
        """Deadline colored red if overdue, yellow otherwise; gray for a done task."""

        if todo.due is None:
            return Text()

        if section_of(todo) != LIVE:
            color = self._muted(self.theme.foreground1)
        else:
            color = self.theme.red if todo.is_overdue else self.theme.yellow

        return Text(f"{DATE_ICON} {day_label(todo.due)}", style=Style(color=color))

    def _project(self, candidate: Candidate) -> Text:
        if not candidate.project:
            return Text()

        theme = self.theme

        if candidate.section == LIVE:
            color = blend(theme.primary, theme.background2, FADE)
        else:
            color = self._muted(theme.foreground1)

        return Text(f"{PROJECT_ICON} {candidate.project}", style=Style(color=color))
