"""
The finder: every task in the database, narrowed down as it is typed

The old search filtered the pane that happened to be in front -- it could only
find what was already on screen, and finding it left the pane greyed out until
escape was pressed. What a search is actually for here is the other thing: a
task is somewhere in the tree, and the point is to get to it.

So this looks through every task there is, whichever project it is filed under
and whether or not it is still to be done, and what it hands back is the one
that was picked. Where the app then goes is `MainScreen.reveal_todo`'s
business.

A query that starts with `>` looks through what the tasks' notes say instead,
and nothing else: the prefix is a way of saying the words are in a note, and a
task whose title happens to say them is not what was asked for. What comes
back is still a task, along with the line of its note the words were found on,
so the note can be opened there.
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
from textual import events
from textual.app import ComposeResult
from textual.screen import ModalScreen
from textual.widgets import Static

from todooit.api import BIN, COMPLETED, Todo, manager
from todooit.api.fixed_projects import owning_project, project_path
from todooit.api.theme import DooitThemeBase
from todooit.ui.widgets.inputs._input import Input
from todooit.ui.widgets.trees.model_tree import GroupHeading
from todooit.utils import blend, day_label
from todooit.utils.links import drawn_column, fold_links

from .base import BaseScreen

# What the panel is titled, in the border, the way quick add is
PANEL_TITLE = "Find task"
NOTES_TITLE = "Find in notes"

# What a query starts with to be looked for in the notes rather than in the
# tasks. Only at the very front: anywhere else it is a letter like any other
NOTE_PREFIX = ">"

# The glyph the query is typed after, the same one the one line entry uses:
# both are a line typed over the app rather than a field in it
PROMPT = "❯ "

# The folder the projects pane draws its rows with, so the project a task was
# found in is recognisably the row over there
PROJECT_ICON = "󰉋"

# The checkbox the tasks pane draws its rows with, empty and ticked
CHECKBOX_EMPTY = "󰄱"
CHECKBOX_TICKED = "󰄵"

# The calendar a deadline is marked with in the date columns
DATE_ICON = "󰃰"

# How many matches are on screen at once. The rest are still there: the cursor
# scrolls the window over them, and the border says where in the list it is
MAX_ROWS = 10

# The same, while the notes are being looked through. Each match takes two
# lines there, the task and the line of its note, so fewer of them fit in the
# room ten single lines take
MAX_NOTE_ROWS = 5

# How much of a note line is kept in front of the word it was found by, when
# the line has to be cut to show it. Enough to read the word in its sentence
SNIPPET_LEAD = 24

# How far the line of a note is stepped in under the task it was found in
SNIPPET_INDENT = "  "

# How far the things around a match are pulled towards the background: the
# project it is in, and the line that stands in for the results while there
# are none
FADE = 0.45

# How far a task that is no longer being worked on is pulled towards it. Far
# enough that the block reads as gray at a glance, and not so far that it
# cannot be read at all -- the same thing the projects pane does to the two
# rows these come from
MUTED_FADE = 0.55

# What the counter in the bottom border says: where the cursor is in the whole
# list of matches, which is the only place the ones off screen are counted
POSITION = "{} of {}"

HINT = "↑↓  move      enter  go to task      esc  cancel"
NOTES_HINT = "↑↓  move      enter  open note      esc  cancel"

# What stands where the results go while there is nothing to put there. The
# empty one is the first thing seen, so it is where the prefix is mentioned
EMPTY_QUERY = f"Type to find a task, {NOTE_PREFIX} for notes"
NO_MATCHES = "No task matches"
EMPTY_NOTE_QUERY = "Type to find in notes"
NO_NOTE_MATCHES = "No note matches"

# The marks a line of a note opens with that say what kind of line it is -- a
# bullet, a numbered item, a quote, a heading -- and not what it says. The
# note draws them as glyphs; out here they would only be clutter
LINE_MARKER = re.compile(r"^\s*(?:(?:[-*+]|\d+[.)]|>+|#+)\s+)*")

# The blocks the matches are drawn in, in the order they are drawn. What is
# still to be done comes first and unheaded, since that is what the finder is
# opened for; the other two are what became of a task, and each is headed by
# the name of the pane it moved to
LIVE, DONE, BINNED = 0, 1, 2

SECTION_LABELS = {DONE: COMPLETED.title, BINNED: BIN.title}


def task_root(todo: Todo) -> Todo:
    """
    The task a todo belongs to: itself, unless it is a step of another one
    """

    node = todo

    while node.parent_todo is not None:
        node = node.parent_todo

    return node


def section_of(todo: Todo) -> int:
    """
    Which block a task is drawn in, which is also where it is to be found

    A task follows its family: a step is wherever the task it belongs to went,
    since that is the pane it is drawn in. A finished step of a task still
    being worked on has gone nowhere, and stays among the live rows.
    """

    if todo.is_binned:
        return BINNED

    if not task_root(todo).pending:
        return DONE

    return LIVE


class NoteHit(NamedTuple):
    """
    Where in a note the query was found: the line, and the column in it

    Counted in the note as it is stored, which is also how the note window
    counts its rows. The column is the one the first word typed starts at.
    """

    row: int
    column: int
    line: str


class Candidate(NamedTuple):
    """
    A task, with everything the query is matched against worked out once

    The list is built when the finder opens and read on every keystroke, so
    the project paths are walked once rather than once per letter.
    """

    todo: Todo
    project: str
    haystack: str
    section: int
    # Filled in on the matches of a search through the notes, and only there
    hit: Optional[NoteHit] = None


class Found(NamedTuple):
    """
    What the finder hands back: the task picked, and where in its note to
    open it when it was found in one
    """

    todo: Todo
    hit: Optional[NoteHit] = None


def note_query(query: str) -> Optional[str]:
    """
    What is to be looked for in the notes, or None when the query is not one
    """

    if not query.startswith(NOTE_PREFIX):
        return None

    return query[len(NOTE_PREFIX) :]


def load_notes() -> Dict[int, str]:
    """
    Every note there is to look through, by the id of the task it belongs to

    One query for all of them rather than one per task: the note is left
    behind whenever a task is read, and the pool was built without them.
    Only the notes with something in them, since an empty one answers nothing.
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
        project = owning_project(todo)
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
    """
    Sorts the dated tasks by their deadline, and the undated ones after them
    """

    if todo.due is None:
        return (1, datetime.max)

    return (0, todo.due)


def rank(candidate: Candidate, terms: Sequence[str]) -> Optional[tuple]:
    """
    How well a task answers the query, or None when it does not answer it

    Every word typed has to turn up somewhere -- in the description or in the
    project path -- which is what lets a task be found by where it is as well
    as by what it says ("api tests"). The work still to do comes first
    whatever it says, since a finished task is usually being looked up rather
    than looked for.

    Within a block what decides the order is the first word alone: a
    description that starts with it, then one with a word starting with it,
    then one that merely contains it, then the tasks that only matched on
    their project. And within a rank the nearest deadline leads, since two
    tasks that read alike are told apart by when they are wanted.
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
    """
    How well a task's note answers the query, and where in it, or None

    The same shape as `rank`, with the note standing in for the description:
    every word typed has to turn up somewhere in the note, and the blocks come
    first. Within a block a note with a word starting with the first term
    beats one that merely has it inside a word, then the nearest deadline.

    The line handed back is the first one holding the first term. The others
    may be anywhere in the note, and the first is the one read as the thing
    being looked for.
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
    """
    The tasks whose notes answer the query, best first, each with its line
    """

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
    """
    A line of a note as it is shown under its task

    The mark it opens with is dropped and its links are folded to their
    names, the way the note draws them. And a line whose match is too far
    along to be seen is cut in front of it, so the word it was found by is
    on screen rather than lost past the end of the row.
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
    """
    The words typed marked wherever they landed rather than only at the
    front, which is what shows why a row is in the list at all when the match
    is halfway along it
    """

    lower = text.plain.lower()

    for term in terms:
        start = lower.find(term)

        while start != -1:
            text.stylize(style, start, start + len(term))
            start = lower.find(term, start + len(term))

    return text


def search(pool: Sequence[Candidate], query: str) -> List[Candidate]:
    """
    The tasks that answer the query, best first
    """

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


class SearchScreen(BaseScreen, ModalScreen):
    """
    The panel the query is typed into, over a dimmed copy of the app

    An overlay rather than a bar, for the same reason quick add is one: what
    is being typed is a question, and the answer to it is a list that has to
    go somewhere. The app stays visible behind it, since where the picked task
    is about to be found is over there.
    """

    def __init__(self) -> None:
        super().__init__()

        self._input = Input()
        self._input.is_editing = True

        self._pool: List[Candidate] = []
        self._matches: List[Candidate] = []

        # The notes, fetched the first time a query asks for them and kept
        # for as long as the finder is open. A finder only ever used for
        # tasks never reads a single one
        self._notes: Optional[Dict[int, str]] = None

        # Which of the matches the cursor is on, counted through the whole
        # list rather than through what is on screen. Always the first one
        # after a keystroke: the list is reordered under it, so wherever the
        # cursor had got to means nothing once the query has changed
        self._index = 0

        # The match the window starts at, which is what the cursor pushes
        # along when it walks past either end of it
        self._offset = 0

    @property
    def theme(self) -> DooitThemeBase:
        return self.api.vars.theme

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
        """The words typed, without the prefix that sends them to the notes"""

        query = note_query(self._input.value)

        if query is None:
            query = self._input.value

        return query.lower().split()

    @property
    def panel(self) -> Static:
        return self.query_one("#search-panel", Static)

    @property
    def hint(self) -> Static:
        return self.query_one("#search-hint", Static)

    def compose(self) -> ComposeResult:
        yield Static(id="search-panel")
        yield Static(HINT, id="search-hint")

    def on_mount(self) -> None:
        self.panel.border_title = PANEL_TITLE
        self._pool = candidates()
        self._redraw()

    # ------------------------------------------------------------------
    # Typing
    # ------------------------------------------------------------------

    async def handle_key(self, event: events.Key) -> bool:
        # Every key belongs to the query, including the ones the app binds
        # elsewhere: this is a text field, and `q` is a letter in it
        event.stop()

        key = self.resolve_key(event)

        if key == "escape":
            self.dismiss(None)
            return True

        if key == "enter":
            self.dismiss(self.selected)
            return True

        # The list is walked with the arrows, and with the keys a terminal
        # walks a list with while the hands are still on the letters
        if key in ("down", "ctrl+n"):
            self._move(1)
            return True

        if key in ("up", "ctrl+p"):
            self._move(-1)
            return True

        self._input.keypress(key)
        self._research()

        return True

    @property
    def selected(self) -> Optional[Found]:
        if not self._matches:
            return None

        candidate = self._matches[self._index]

        return Found(candidate.todo, candidate.hit)

    def _move(self, step: int) -> None:
        """
        Moves the cursor through every match, and the window along with it

        The list is walked round rather than stopped at either end: what is
        wanted is usually near the top, and a cursor sent up from there gets
        to the bottom of the list in one key.
        """

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

        # Where the cursor is in a list that mostly does not fit: without it a
        # window scrolled halfway down says nothing about how much is left
        self.panel.border_subtitle = (
            POSITION.format(self._index + 1, len(self._matches))
            if self._matches
            else ""
        )

    def _line(self) -> Text:
        # The buffer draws itself rather than being handed over as a string,
        # so that a selection made in it is highlighted here too
        buffer = self._input.render_editing(self.theme)
        buffer.style = Style(color=self.theme.foreground3)

        return Text(PROMPT, style=Style(color=self.theme.primary, bold=True)) + buffer

    def _faded(self, message: str) -> Text:
        return Text(
            message,
            style=Style(
                color=blend(self.theme.foreground1, self.theme.background2, FADE)
            ),
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

        # Grouped rather than sliced by section: a window scrolled into the
        # middle of the list can hold the end of one block and the start of
        # the next, and each still has to be drawn under its own name
        for section, rows in groupby(window, key=lambda row: row[1].section):
            if section != LIVE:
                blocks.append(self._heading(section, space_above=bool(blocks)))

            blocks.append(self._table(list(rows), terms, widths))

        return Group(*blocks)

    def _heading(self, section: int, space_above: bool) -> GroupHeading:
        """
        The name of a block, with a hairline running out to the panel edge

        The same heading the tasks pane divides its blocks with, so a run of
        rows under a name reads the same here as it does over there.
        """

        theme = self.theme

        return GroupHeading(
            label=SECTION_LABELS[section],
            label_style=blend(theme.foreground1, theme.background2, FADE),
            rule_style=theme.background3,
            space_above=space_above,
        )

    def _column_widths(self, window: Iterable[Candidate]) -> Tuple[int, int]:
        """
        How wide the deadline and the project are drawn, across every block

        Fixed here rather than left to each block's own table, or the columns
        would step sideways at every heading: what a block holds says nothing
        about where the columns of the panel are.
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
        # Filled to the width of the panel rather than to the longest row, so
        # that the project a task is in lines up down the right hand side and
        # the cursor is a band rather than a ragged patch
        table = Table.grid(expand=True, padding=(0, 1))
        table.add_column(width=1)
        table.add_column(ratio=1, no_wrap=True, overflow="ellipsis")
        table.add_column(justify="right", no_wrap=True, width=widths[0])
        table.add_column(justify="right", no_wrap=True, width=widths[1])

        for index, candidate in rows:
            style = self._row_style(index)

            table.add_row(
                self._status(candidate),
                # Found through its note, the words are not in the title, and
                # picking them out there would say they were
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
        """A color as a task nobody is working on any more wears it"""

        return blend(color, self.theme.background2, MUTED_FADE)

    def _status(self, candidate: Candidate) -> Text:
        """
        The checkbox the row wears in the pane, in the color its priority
        gives it there -- and gray, like everything else on the row, once the
        task is done with
        """

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
        """
        What the task says, with what was typed picked out of it

        The words are marked wherever they landed rather than only at the
        front, which is what shows why a row is in the list at all when the
        match is halfway down a long description.
        """

        theme = self.theme
        live = candidate.section == LIVE
        color = theme.foreground2 if live else self._muted(theme.foreground1)
        accent = theme.primary if live else self._muted(theme.primary)

        text = Text(candidate.todo.description, style=Style(color=color))

        return picked_out(text, terms, Style(color=accent, bold=True))

    def _snippet(self, candidate: Candidate, terms: Sequence[str]) -> Text:
        """
        The line of the note the task was found by, under the task

        Dimmer than the row above it, since it is what explains the row and
        not the row itself, with the words typed picked out of it the way a
        description has them picked out.
        """

        hit = candidate.hit
        assert hit is not None

        theme = self.theme
        live = candidate.section == LIVE
        color = blend(theme.foreground1, theme.background2, FADE)
        accent = theme.primary if live else self._muted(theme.primary)

        if not live:
            color = self._muted(theme.foreground1)

        text = Text(snippet(hit.line, hit.column), style=Style(color=color))
        text = picked_out(text, terms, Style(color=accent, bold=True))

        # Stepped in under the title, so it reads as belonging to the row
        return Text(SNIPPET_INDENT) + text

    def _due(self, todo: Todo) -> Text:
        """
        The deadline, if the task has one: overdue in red and still ahead in
        yellow, the way the date columns are colored. A task that is over with
        is late for nothing, so its date is drawn gray with the rest of it.
        """

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
