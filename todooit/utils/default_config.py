from datetime import date, datetime, timedelta
from functools import partial
from typing import Callable, Optional, Tuple

from rich.style import Style
from rich.text import Text

from todooit.api import Cadence, Project, Todo, TodoSortModeType
from todooit.ui.api import TodooitAPI, extra_formatter, subscribe, timer
from todooit.ui.api.bar_widgets import clock, current_project, spacer, text
from todooit.ui.api.events import ModeChanged, Startup
from todooit.ui.api.formatter_presets import (
    description_highlight_link,
    due_danger_today,
    recurrence_icon,
)
from todooit.ui.api.todooit_api import SORT_LABELS
from todooit.ui.api.widgets import ProjectWidget, TodoWidget
from todooit.ui.widgets.bars import StatusBarWidget
from todooit.utils import DATE_FORMAT, WEEKDAY_NAMES, blend, day_label
from todooit.vim_engine import VimCommand, VimMotion, VimOperator, VimTextObject

# Todo formatters


# The child count trailing a collapsed project or todo shares one color: the
# accent the column headers are drawn in, pulled towards the background so the
# number annotates the row it sits on instead of competing with it.
COUNT_FADE = 0.4


def count_color(api: TodooitAPI) -> str:
    return blend(api.vars.theme.primary, api.vars.theme.background1, COUNT_FADE)


# Priority 1 is the most urgent one; 0 means no priority was set
PRIORITIES = (1, 2, 3)


def priority_color(priority: int, api: TodooitAPI) -> str:
    theme = api.vars.theme
    colors = {
        1: theme.red,
        2: theme.yellow,
        # p3 is the calm end of the scale, so it takes the theme's light blue
        # rather than a green that reads as "done" beside the due-date colors
        3: theme.cyan,
    }

    # Nothing prioritized: a gray sitting halfway between text and background
    return colors.get(priority, blend(theme.foreground1, theme.background1, 0.5))


# The orders a project's todos can be read in, in the order the help lists
# them. Priority leads because it is the one a project is opened to ask:
# whatever is filed in here, what is the next thing to do out of it. The dates
# are there for the stretches of work that are run off a calendar instead, and
# hold until they are switched back — the order is the pane's, not a project's.
SORT_MODES: Tuple[TodoSortModeType, ...] = ("priority", "due", "scheduled")


CHECKBOX_EMPTY = "󰄱"
CHECKBOX_TICKED = "󰄵"


# A rounded checkbox, ticked once the todo is done. It carries the priority
# color, so a row's urgency reads from the very first column and needs no column
# of its own; the tick only pulls that color a notch towards the background,
# dimming it without draining it the way the other columns get grayed out.
def todo_status_formatter(status: str, todo: Todo, api: TodooitAPI):
    completed = status == "completed"
    color = priority_color(todo.priority, api)

    if completed:
        color = blend(color, api.vars.theme.background1, 0.35)

    return Text(
        CHECKBOX_TICKED if completed else CHECKBOX_EMPTY,
        style=Style(color=color, bold=True),
    )


# A "week" of lead time means five Austrian working days: Sat and Sun don't
# count (public holidays are ignored).
WORKING_DAYS_PER_WEEK = 5


def _add_working_days(start: date, days: int) -> date:
    current = start

    while days:
        current += timedelta(days=1)
        if current.weekday() < 5:
            days -= 1

    return current


# A todo carries two dates: `due`, the deadline it has to be done by, and
# `scheduled`, the day it is planned to be worked on. Both columns are rendered
# by the formatters below, which differ only in the field they read.
#
# German date convention: weekday first, then day, dot separated, and no year
# (see DATE_FORMAT). The time only shows up when it is something other than
# midnight.
def todo_date_formatter(value: Optional[datetime], _: Todo) -> str:
    if value is None:
        return ""

    dt_format = DATE_FORMAT

    if value.hour or value.minute:
        dt_format += " (%H:%M)"

    return f"{WEEKDAY_NAMES[value.weekday()]}, {value.strftime(dt_format)}"


# `date_icon` appends the value it is given to a Text as plain text, which
# escapes whatever markup the value already carried, so one `from_markup` pass
# hands that markup back as literal text rather than dropping it. A second pass
# is what actually strips it.
def _strip_markup(value: str) -> str:
    return Text.from_markup(Text.from_markup(value).plain).plain


DATE_ICON_COMPLETED = "󰃯 "
DATE_ICON_PENDING = "󰃰 "
DATE_ICON_OVERDUE = " "


# The calendar in front of a date, so a date column is recognisable as one from
# across the row. Only the Completed pane's column carries it per row: the
# scheduled and due columns have it once, in their header (TodosTree). It arrives with a status color of its own, which the color
# formatter above it then drops in favor of one style over the whole column.
def date_icon(field: str):
    @extra_formatter
    def wrapper(value: str, todo: Todo, api: TodooitAPI):
        date = getattr(todo, field)

        if not date:
            return value

        theme = api.vars.theme

        if todo.is_completed:
            icon, color = DATE_ICON_COMPLETED, theme.green
        elif date < datetime.now():
            icon, color = DATE_ICON_OVERDUE, theme.red
        else:
            icon, color = DATE_ICON_PENDING, theme.yellow

        return Text() + Text.from_markup(icon, style=Style(color=color)) + value

    return wrapper


# Runs after the calendar icon has been prepended, so icon and date get one
# shared lead-time color. The icon arrives carrying its own status color, and
# "Today" its own bold red, both of which are dropped here in favor of one
# style over the whole column; the result has to be handed back as a markup
# string, since a Text would get escaped by the formatter store.
def date_color_formatter(field: str):
    @extra_formatter
    def wrapper(value: str, todo: Todo, api: TodooitAPI) -> str:
        date = getattr(todo, field)

        if not date:
            return value

        theme = api.vars.theme
        now = datetime.now()
        bold = False

        if todo.is_completed:
            # Nothing is urgent about a done todo
            color = theme.green
        elif date.date() == now.date():
            # Checked ahead of the overdue branch so a todo dated today reads
            # the same whether its time has passed or is still to come: this is
            # the color for the "Today" that `due_danger_today` put in place of
            # the date, and the bold is what sets it apart from merely overdue.
            color = theme.red
            bold = True
        elif date < now:
            color = theme.red
        elif date.date() <= _add_working_days(now.date(), WORKING_DAYS_PER_WEEK):
            color = theme.yellow
        else:
            # A date nobody has to think about yet gets no color of its own,
            # only the theme's white: anything grayer would read as completed
            color = theme.foreground3

        style = f"bold {color}" if bold else color
        return f"[{style}]{_strip_markup(value)}[/]"

    return wrapper


# How many todos hang below this one, at any depth. Only drawn while the todo is
# collapsed: once it is open, the children are right there on the rows below.
def todo_description_formatter(description: str, todo: Todo, api: TodooitAPI) -> str:
    count = todo.total_children

    if not count or api.is_expanded(todo):
        return description

    return f"{description} [{count_color(api)}]({count})[/]"


# A sheet of paper on the rows whose note carries anything - text, files, or
# both - and nothing at all on the ones that do not. The column has no header
# and is only as wide as the icon, so it marks the row without taking any room
# from the description.
NOTE_ICON = ""


def todo_note_formatter(note: str, todo: Todo, api: TodooitAPI) -> str:
    # A file hanging off a note is something the task carries just as much as
    # the text is, so a note holding nothing but an attachment is still a note
    # to open: the column marks it either way, rather than leaving the row
    # looking bare because nothing was typed into it.
    #
    # A space rather than an empty string: the formatter store turns anything
    # falsy into a dim, centered "-", which is not the same as nothing
    if not (note or "").strip() and not (todo.attachments or "").strip():
        return " "

    return f"[{api.vars.theme.foreground3}]{NOTE_ICON}[/]"


def todo_recurrence_formatter(recurrence: Optional[Cadence], _):
    if recurrence is None:
        return ""

    return str(recurrence)


# How far a completed row's text is pulled towards the background. Far enough
# that a done row sinks into the background at a glance, but short of the point
# where the description stops being readable when you go looking for it.
COMPLETED_FADE = 0.55


# A row that has been finished or thrown away is done with: its whole line is
# grayed out, and its description struck through on top of that. The status
# column is left alone, so the check mark stays the one bright thing left on
# the row.
def _gray_out(applies: Callable[[Todo], bool], strike: bool):
    @extra_formatter
    def wrapper(value: str, todo: Todo, api: TodooitAPI):
        if not applies(todo):
            return

        theme = api.vars.theme

        # The colors handed out by the formatters above sit on inner spans,
        # which a base style can't override, so the value is flattened back to
        # plain text before the gray goes on.
        plain = Text.from_markup(value).plain

        # `dim` on its own is a hint that plenty of terminals ignore, so the
        # fade is baked into the color and dim just rides along on top.
        return Text(
            plain,
            style=Style(
                color=blend(theme.foreground1, theme.background1, COMPLETED_FADE),
                dim=True,
                strike=strike,
            ),
        ).markup

    return wrapper


def gray_out_completed(strike: bool = False):
    return _gray_out(lambda todo: todo.is_completed, strike)


# The Bin is read the way the completion log is, so the rows in it are drawn
# the same way: struck through and sunk into the background, because they are
# not work any more either
def gray_out_binned(strike: bool = False):
    return _gray_out(lambda todo: todo.is_binned, strike)


# The waste basket in front of the date a row was thrown away on, the same one
# the Bin itself is drawn with. It carries the muted gray the rest of the row
# is faded to rather than a status color: nothing about a binned row is urgent,
# and the date is only there to say how long ago you changed your mind.
BIN_DATE_ICON = "󰆴 "


@extra_formatter
def binned_date_formatter(value: str, todo: Todo, api: TodooitAPI) -> str:
    if not todo.binned_at:
        return value

    theme = api.vars.theme
    color = blend(theme.foreground1, theme.background1, COMPLETED_FADE)

    return f"[{color}]{BIN_DATE_ICON}{_strip_markup(value)}[/]"


# Project formatters


# Projects can be colored the way folders and labels are: ten slots, typed
# straight in as c0 through c9, with the colors that get reached for first at
# the low digits and the two a list of color names runs out on at the end.
PROJECT_COLOR_NAMES = (
    "red",
    "blue",
    "green",
    "yellow",
    "orange",
    "purple",
    "cyan",
    "pink",
    "brown",
    "olive",
)


# A project's color is its own label and says nothing about the work inside
# it -- which is exactly what a priority or a due date does say. So none of
# these is a shade those are drawn in: every named color is pulled a quarter
# of the way towards the pane's own text first, which lifts the whole family
# clear of the signal colors without moving any of them off its hue.
PROJECT_COLOR_LIFT = 0.25

# The two the palette ends on are earth tones rather than hues of their own: an
# orange and a green, each taken down towards the ground instead of lifted
# towards the text. Neither has a signal color to be told apart from, and a
# gray is deliberately not among them -- the pane already draws a project it is
# done with in gray, and a project colored gray on purpose would be read as one
# of those.
PROJECT_MUTED_FADE = 0.45


def project_palette(api: TodooitAPI) -> Tuple[str, ...]:
    """
    The ten colors a project can be given, in the order the digits hand them out
    """

    theme = api.vars.theme

    def lift(color: str) -> str:
        return blend(color, theme.foreground3, PROJECT_COLOR_LIFT)

    return (
        lift(theme.red),
        lift(theme.blue),
        lift(theme.green),
        lift(theme.yellow),
        lift(theme.orange),
        lift(theme.purple),
        lift(theme.cyan),
        # Halfway between the theme's magenta and its red, so the pink lands as
        # a pink instead of as a second purple beside the one above it
        lift(blend(theme.magenta, theme.red, 0.5)),
        blend(theme.orange, theme.background1, PROJECT_MUTED_FADE),
        blend(theme.green, theme.background1, PROJECT_MUTED_FADE),
    )


def project_color(project, api: TodooitAPI) -> Optional[str]:
    """
    The color a project was given, or None for one that was never colored

    A fixed project belongs to the app rather than to the database and has no
    slot to be in, which reads here as never having picked one.
    """

    slot = getattr(project, "color", None)

    if slot is None:
        return None

    palette = project_palette(api)

    if not 0 <= slot < len(palette):
        return None

    return palette[slot]


# The folder every stored project is drawn with, the same one the status bar
# marks the current project with. A fixed project brings an icon of its own
# instead, which is what tells the two kinds apart at a glance.
PROJECT_ICON = "󰉋"

# How far the folder is pulled towards the background: enough that a column of
# them stays quiet behind the names it marks
PROJECT_ICON_FADE = 0.35


# Runs after the sub project count has been appended, so the icon is the very
# first thing on the row whatever else the name picked up along the way. A
# fixed project takes the accent, since it is part of the app rather than one
# more thing in the list.
@extra_formatter
def project_icon_formatter(name: str, project, api: TodooitAPI) -> str:
    theme = api.vars.theme

    if getattr(project, "is_fixed", False):
        icon, color = project.icon, theme.primary
    else:
        icon = PROJECT_ICON
        # A colored project paints its folder in full: the quiet gray is what
        # an uncolored one gets, and a color on the row is worth more than the
        # fade that keeps a column of plain folders out of the way
        color = project_color(project, api) or blend(
            theme.foreground1, theme.background1, PROJECT_ICON_FADE
        )

    return f"[{color}]{icon}[/] {name}"


# How far a muted project is pulled towards the background: the same fade a
# completed todo gets, and for the same reason — it is done with, and only
# looked at on purpose.
MUTED_PROJECT_FADE = COMPLETED_FADE


# A project that is never worked out of is drawn in one flat gray, icon and
# all. The accent the fixed projects otherwise carry would put it on a level
# with Today, which is where the day actually starts.
@extra_formatter
def gray_out_muted_project(value: str, project, api: TodooitAPI):
    if not getattr(project, "muted", False):
        return

    theme = api.vars.theme

    # The colors handed out by the formatters above sit on inner spans, which a
    # base style can't override, so the value is flattened before the gray
    plain = Text.from_markup(value).plain

    return Text(
        plain,
        style=Style(
            color=blend(theme.foreground1, theme.background1, MUTED_PROJECT_FADE),
            dim=True,
        ),
    ).markup


# How many projects hang below this one, at any depth. Only drawn while the
# project is collapsed: once it is open, the sub projects are right there on the
# rows below.
def project_description_formatter(
    description: str, project: Project, api: TodooitAPI
) -> str:
    count = project.total_projects

    if not count or api.is_expanded(project):
        return description

    return f"{description} [{count_color(api)}]({count})[/]"


# Runs before the icon is put in front of the name, so the color wraps the name
# alone and the folder is painted separately. The sub project count carries a
# color of its own on an inner span and keeps it: it is the pane counting, not
# part of what the project is called.
@extra_formatter
def project_color_formatter(name: str, project, api: TodooitAPI) -> Optional[str]:
    color = project_color(project, api)

    if color is None:
        return None

    return f"[{color}]{name}[/]"


@subscribe(Startup)
def vim_key_setup(api: TodooitAPI, _):
    # The keys inside a note's text, apart from the panes' own
    api.vim.keys.set("j", VimMotion.LEFT)
    api.vim.keys.set("ö", VimMotion.RIGHT)
    api.vim.keys.set("k", VimMotion.UP)
    api.vim.keys.set("l", VimMotion.DOWN)
    api.vim.keys.set("w", VimMotion.WORD_FORWARD)
    api.vim.keys.set("b", VimMotion.WORD_BACKWARD)
    api.vim.keys.set("e", VimMotion.WORD_END)
    api.vim.keys.set("=", VimMotion.FIRST_NON_BLANK)
    api.vim.keys.set("_", VimMotion.LAST_CHARACTER)
    api.vim.keys.set("ü", VimMotion.LINE_ABOVE)
    api.vim.keys.set("ä", VimMotion.LINE_BELOW)
    api.vim.keys.set("f", VimMotion.FIND_FORWARD)
    api.vim.keys.set("F", VimMotion.FIND_BACKWARD)
    api.vim.keys.set("t", VimMotion.TILL_FORWARD)
    api.vim.keys.set("T", VimMotion.TILL_BACKWARD)
    api.vim.keys.set("h", VimMotion.REPEAT_FIND)
    api.vim.keys.set("H", VimMotion.REVERSE_FIND)
    api.vim.keys.set("<ctrl+u>", VimMotion.HALF_PAGE_UP)
    api.vim.keys.set("<ctrl+d>", VimMotion.HALF_PAGE_DOWN)
    api.vim.keys.set("gg", VimMotion.TOP)
    api.vim.keys.set("G", VimMotion.BOTTOM)
    api.vim.keys.set("{", VimMotion.PARAGRAPH_UP)
    api.vim.keys.set("}", VimMotion.PARAGRAPH_DOWN)
    api.vim.keys.set("n", VimMotion.SEARCH_NEXT)
    api.vim.keys.set("N", VimMotion.SEARCH_PREVIOUS)
    api.vim.keys.set("s", VimMotion.VIM_FLASH)
    api.vim.keys.set("i", VimCommand.INSERT)
    api.vim.keys.set("a", VimCommand.INSERT_AFTER)
    api.vim.keys.set("I", VimCommand.INSERT_FIRST_NON_BLANK)
    api.vim.keys.set("A", VimCommand.INSERT_LINE_END)
    api.vim.keys.set("gi", VimCommand.INSERT_AT_LAST)
    api.vim.keys.set("o", VimCommand.OPEN_BELOW)
    api.vim.keys.set("O", VimCommand.OPEN_ABOVE)
    api.vim.keys.set("zz", VimCommand.CENTER_VIEW)
    api.vim.keys.set("gx", VimCommand.OPEN_LINK)
    api.vim.keys.set("gf", VimCommand.PICK_FILES)
    api.vim.keys.set("d", VimOperator.DELETE)
    api.vim.keys.set("dd", VimCommand.DELETE_LINE)
    api.vim.keys.set("D", VimCommand.DELETE_TO_LINE_END)
    api.vim.keys.set("x", VimCommand.DELETE_CHAR)
    api.vim.keys.set("c", VimOperator.CHANGE)
    api.vim.keys.set("cc", VimCommand.CHANGE_LINE)
    api.vim.keys.set("C", VimCommand.CHANGE_TO_LINE_END)
    api.vim.keys.set(">", VimOperator.INDENT)
    api.vim.keys.set(">>", VimCommand.INDENT_LINE)
    api.vim.keys.set("<", VimOperator.UNINDENT)
    api.vim.keys.set("<<", VimCommand.UNINDENT_LINE)
    api.vim.keys.set("ip", VimTextObject.INNER_PARAGRAPH)
    api.vim.keys.set("ap", VimTextObject.AROUND_PARAGRAPH)
    api.vim.keys.set("iw", VimTextObject.INNER_WORD)
    api.vim.keys.set("aw", VimTextObject.AROUND_WORD)
    api.vim.keys.set(["iW", "i "], VimTextObject.INNER_BIG_WORD)
    api.vim.keys.set("aW", VimTextObject.AROUND_BIG_WORD)
    # Either half of a pair names it
    for inner, around, pair in (
        (VimTextObject.INNER_PARENS, VimTextObject.AROUND_PARENS, "()"),
        (VimTextObject.INNER_BRACKETS, VimTextObject.AROUND_BRACKETS, "[]"),
        (VimTextObject.INNER_BRACES, VimTextObject.AROUND_BRACES, "{}"),
        (VimTextObject.INNER_ANGLES, VimTextObject.AROUND_ANGLES, "<>"),
        (VimTextObject.INNER_DOUBLE_QUOTES, VimTextObject.AROUND_DOUBLE_QUOTES, '"'),
        (VimTextObject.INNER_SINGLE_QUOTES, VimTextObject.AROUND_SINGLE_QUOTES, "'"),
        (VimTextObject.INNER_BACKTICKS, VimTextObject.AROUND_BACKTICKS, "`"),
    ):
        api.vim.keys.set([f"i{char}" for char in pair], inner)
        api.vim.keys.set([f"a{char}" for char in pair], around)
    api.vim.keys.set("r", VimCommand.REPLACE_CHAR)
    api.vim.keys.set("y", VimOperator.YANK)
    api.vim.keys.set("yy", VimCommand.YANK_LINE)
    api.vim.keys.set("p", VimCommand.PASTE_AFTER)
    api.vim.keys.set("P", VimCommand.PASTE_BEFORE)
    api.vim.keys.set("u", VimCommand.UNDO)
    api.vim.keys.set("<ctrl+r>", VimCommand.REDO)
    api.vim.keys.set("?", VimCommand.SEARCH)
    api.vim.keys.set("*", VimCommand.SEARCH_WORD)


@subscribe(Startup)
def key_setup(api: TodooitAPI, _):
    # Groups show up as sections in the help screen, in this order
    NAVIGATION = "Navigation"
    EDITING = "Editing"
    MOVING = "Moving & Clipboard"
    VIEW = "Search & View"

    api.keys.set("j", api.focus_projects, group=NAVIGATION)
    api.keys.set("ö", api.focus_todos, group=NAVIGATION)
    api.keys.set("k", api.move_up, group=NAVIGATION)
    api.keys.set("l", api.move_down, group=NAVIGATION)
    api.keys.set("gg", api.go_to_top, group=NAVIGATION)
    api.keys.set("gt", api.goto_today, group=NAVIGATION)
    api.keys.set("gu", api.goto_upcoming, group=NAVIGATION)
    api.keys.set("gc", api.goto_completed, group=NAVIGATION)
    api.keys.set("gb", api.goto_bin, group=NAVIGATION)
    # The way back from a pane that gathered its rows from elsewhere: the task
    # under the cursor, in the project it actually lives in. Among the other
    # "g" jumps because it is one -- those name the pane to go to, this one
    # lets the highlighted row name it -- and scoped to the tasks, since a
    # project row is already standing in its own pane
    api.keys.set("gi", api.goto_item, group=NAVIGATION, scope="todos")
    api.keys.set("G", api.go_to_bottom, group=NAVIGATION)
    # Flash mode, "f" for "flash": a label on every row on screen in this pane,
    # and typing one lands the cursor there -- the way to a row you can see
    # without counting how far away it is
    api.keys.set("f", api.flash_jump, group=NAVIGATION)
    # The desktop's top/bottom of a document too (a Mac's cmd+up/down,
    # passed on by the terminal); hidden, as gg/G already say it in help
    api.keys.set("<ctrl+home>", api.go_to_top, group=NAVIGATION, hidden=True)
    api.keys.set("<ctrl+end>", api.go_to_bottom, group=NAVIGATION, hidden=True)
    api.keys.set("h", api.toggle_expand, group=NAVIGATION)

    api.keys.set("i", api.edit_description, group=EDITING)
    api.keys.set("d", api.edit_due, group=EDITING)
    # Lowercase, matching the other date: the sorting chords below moved up to
    # the shifted "S" to leave this one free, since a key that is the start of
    # another one can never be pressed on its own
    api.keys.set("s", api.edit_scheduled, group=EDITING)
    api.keys.set("r", api.edit_recurrence, group=EDITING)
    api.keys.set("n", api.add_sibling, group=EDITING)
    api.keys.set("N", api.add_child_node, group=EDITING)
    # The whole task in one line, from wherever the cursor happens to be. The
    # shifted twin of the key that ticks one off, since between them they are
    # the two ends of a task's life
    api.keys.set("C", api.quick_add, group=EDITING)
    api.keys.set(" ", api.show_note, group=EDITING)
    # The scratchpad, next to the key that opens a todo's note: the same
    # window, for the thoughts that have no task to be written on yet
    api.keys.set("m", api.show_pinned_note, group=EDITING)
    # Scoped to the todos, because over the projects the very same key opens
    # the color chords below: a key that is the start of another one can never
    # be pressed on its own, and there is nothing in the left pane to tick off
    # anyway
    api.keys.set("c", api.toggle_complete, group=EDITING, scope="todos")
    # Throwing something away costs nothing and asks nothing: it goes to the
    # Bin, where "R" fetches it back. Getting rid of it for real is the other
    # chord, which is the one that stops to ask
    api.keys.set("xx", api.remove_node, group=EDITING)
    api.keys.set("yy", api.delete_node, group=EDITING)
    api.keys.set("R", api.restore_node, group=EDITING)
    # The shifted twin of the chord that deletes one task for good, and the
    # same thing over a whole pane: in the Bin it empties the Bin, in
    # Completed it clears out everything finished, and anywhere else it does
    # nothing but say where it works. It says how much is about to go before
    # it goes. A chord rather than the single shifted key, since a whole pane
    # is far too much to lose to a slip of the finger — it has to be typed
    # twice over, the way "yy" does
    api.keys.set("YY", api.empty_pane, group=EDITING)

    # Taking back the last thing that happened, on the same keys as inside a
    # note, so that undo means one thing everywhere.
    #
    # What they walk back is every edit either pane can make, one key at a
    # time, however much of the tree that key moved.
    api.keys.set("u", api.undo, group=EDITING)
    api.keys.set("<ctrl+r>", api.redo, group=EDITING)

    # A scale is one thing to learn, not four, so the whole run of digits is
    # listed as the single row it reads as. The keys are still set one at a
    # time; it is only the help screen that is told to write them as a range.
    PRIORITY_LABEL = f"p0-p{max(PRIORITIES)}"
    PRIORITY_HELP = (
        f"Set the todo priority, p1 the most urgent "
        f"and p{max(PRIORITIES)} the least (p0 clears it)"
    )

    for priority in [0, *PRIORITIES]:
        api.keys.set(
            f"p{priority}",
            partial(api.set_priority, priority),
            description=PRIORITY_HELP,
            group=EDITING,
            label=PRIORITY_LABEL,
        )

    # A color is picked off the palette the way a priority is picked off its
    # scale, and typed the same way: the chord says which slot, and pressing
    # the slot a project is already in takes the color back off. What it is
    # given to is the whole tree the highlighted project is in, since a color
    # labels a project and everything filed under it. The digits are
    # named in the one row the whole run collapses to, which is where ten
    # colors are looked up once instead of being learnt as ten bindings.
    COLOR_LABEL = f"c0-c{len(PROJECT_COLOR_NAMES) - 1}"
    COLOR_NAMED = ", ".join(
        f"c{slot} {name}" for slot, name in enumerate(PROJECT_COLOR_NAMES)
    )
    COLOR_HELP = (
        f"Color the project and everything filed under it: {COLOR_NAMED} "
        "(the same key again takes the color off)"
    )

    for slot in range(len(PROJECT_COLOR_NAMES)):
        api.keys.set(
            f"c{slot}",
            partial(api.set_project_color, slot),
            description=COLOR_HELP,
            group=EDITING,
            label=COLOR_LABEL,
            scope="projects",
        )

    api.keys.set("L", api.shift_down, group=MOVING)
    api.keys.set("K", api.shift_up, group=MOVING)
    # A row moves sideways as well as up and down: shifted "i" files it under
    # the row above it, shifted "u" pulls it back out. Tasks and projects
    # both nest, so the two keys work the same in either pane
    api.keys.set("I", api.indent, group=MOVING)
    api.keys.set("U", api.unindent, group=MOVING)
    # The move that crosses the whole tree rather than one step of it: the
    # other three shift a task among the rows around it, and this one takes it
    # out of the project altogether. Shifted "m", which is free over the tasks
    # — plain "m" is the pinned note, and nothing else starts with either
    api.keys.set("M", api.move_todo, group=MOVING, scope="todos")
    # The clipboard is the system one, so it is worked with the keys the rest
    # of the desktop uses rather than vim's
    api.keys.set("<ctrl+c>", api.copy_description_to_clipboard, group=MOVING)
    # The note beside the description, on the key it is named after: the whole
    # of a task's note, taken without the note screen ever coming up
    api.keys.set("<ctrl+n>", api.copy_note_to_clipboard, group=MOVING)
    api.keys.set("<ctrl+v>", api.paste_as_sibling, group=MOVING)

    # "o" for open: the link the row is standing on (inside a note it's `gx`)
    api.keys.set("o", api.open_link, group=VIEW)
    # "/" opens the finder over the app rather than filtering the pane in
    # front: what a search is for here is a task somewhere else in the tree,
    # and enter walks the cursor over to it
    api.keys.set("/", api.start_search, group=VIEW)
    # The way out of todooit: ctrl+c is a copy here, as it is everywhere else
    api.keys.set("q", api.quit, group=VIEW)

    # The order a project is read in, typed as one chord per order: shifted
    # "S" then the shifted initial of the thing sorted by. Shifted, so that
    # plain "s" is left to the scheduled date rather than being swallowed as
    # the prefix of these. They are one row in the help for the same reason
    # the priority scale is — three ways of asking the same question, and a
    # list of them is read as a list, not as three bindings.
    SORT_LABEL = "S" + "/S".join(mode[0].upper() for mode in SORT_MODES)
    SORT_HELP = "Sort the todos by " + ", ".join(
        SORT_LABELS[mode] for mode in SORT_MODES
    )

    for mode in SORT_MODES:
        api.keys.set(
            f"S{mode[0].upper()}",
            partial(api.sort_todos, mode),
            description=SORT_HELP,
            group=VIEW,
            label=SORT_LABEL,
        )

    api.keys.set(
        "?",
        api.show_help,
        description="Show the help screen",
        group=VIEW,
        hidden=True,
    )


@subscribe(Startup)
def layout_setup(api: TodooitAPI, _):
    # The projects pane takes the width its widest row needs with every project
    # expanded, so folding never shifts the split, and the tasks pane the rest.
    # Capped at a quarter of the screen, the most the old fixed split ever gave
    # it: past that, long names wrap as they always have. Off, the split goes
    # back to that fixed quarter.
    api.vars.projects_pane_auto_width = True
    api.vars.projects_pane_max_width = 0.25

    api.layouts.project_layout = [
        ProjectWidget.description,
    ]
    api.layouts.todo_layout = [
        TodoWidget.status,
        TodoWidget.description,
        # The two dates sit side by side, right after the description: the day
        # the work is planned for, then the day it is owed by, so the plan and
        # the deadline are read as the pair they are
        TodoWidget.scheduled,
        TodoWidget.due,
        TodoWidget.recurrence,
        # Last on the row: a note is something a todo either has or has not,
        # read in one glance and never scanned against the columns beside it
        TodoWidget.note,
    ]


@subscribe(Startup)
def formatter_setup(api: TodooitAPI, _):
    # Added first => runs last, so the graying has the final say over every
    # color the formatters below hand out
    for gray_out in (gray_out_binned, gray_out_completed):
        api.formatter.todos.description.add(gray_out(strike=True))
        api.formatter.todos.due.add(gray_out())
        api.formatter.todos.scheduled.add(gray_out())
        api.formatter.todos.recurrence.add(gray_out())
        api.formatter.todos.note.add(gray_out())

    api.formatter.todos.status.add(todo_status_formatter)
    api.formatter.todos.description.add(todo_description_formatter)

    # URLs are picked out of the raw description, so this has to run before
    # the child count appends its own markup: added last => runs first.
    api.formatter.todos.description.add(description_highlight_link())

    # Every date column is built the same way, out of the same formatters. The
    # completion date is only ever drawn in the Completed project, where it
    # stands in for the two columns above: it comes out green throughout, since
    # the row it is on is done and nothing about it can be late any more
    for column, field in (
        (api.formatter.todos.due, "due"),
        (api.formatter.todos.scheduled, "scheduled"),
        (api.formatter.todos.completed, "completed_at"),
    ):
        column.add(todo_date_formatter)
        # Value formatters stop at the first one that returns something, so
        # this has to sit after the date formatter to get the first look: on
        # the day itself it swallows the date and puts a plain "Today" there
        # instead, and on any other day it declines and lets the date through.
        column.add(due_danger_today())
        column.add(date_color_formatter(field))

        # The scheduled and due columns carry the calendar once, in their
        # header, rather than on every row
        if field == "completed_at":
            column.add(date_icon(field))  # added last => runs first

    # The Bin's own date column, built out of the same date formatter, read a
    # day at a time the way the completion log is, and then marked and colored
    # by the one thing it has to say, which is that the row is in the Bin
    api.formatter.todos.binned.add(todo_date_formatter)
    api.formatter.todos.binned.add(due_danger_today())
    api.formatter.todos.binned.add(binned_date_formatter)

    api.formatter.todos.note.add(todo_note_formatter)
    api.formatter.todos.recurrence.add(todo_recurrence_formatter)
    # Marks the repeating todos, whose interval is easy to miss as bare text
    api.formatter.todos.recurrence.add(recurrence_icon())

    # Added first => runs last, so the gray has the final say over the icon and
    # the count every formatter below hands out
    api.formatter.projects.description.add(gray_out_muted_project)

    # Added before the one below it => runs after it, so the icon ends up in
    # front of everything that formatter appends to the name, and the name is
    # already colored by the time the icon joins it
    api.formatter.projects.description.add(project_icon_formatter)
    api.formatter.projects.description.add(project_color_formatter)
    api.formatter.projects.description.add(project_description_formatter)


# Status bar


# The bar is a powerline: every widget paints a solid block of background, and
# the rounded caps between them belong to the block they open — drawn in that
# block's color, over the color of the block they leave behind.
ROUND_OPEN = ""
ROUND_CLOSE = ""


# What the caps at either end of a chain sit on: the bar's own background
def bar_background(api: TodooitAPI) -> str:
    return api.vars.theme.background2


MODE_COLORS = {
    "NORMAL": "primary",
    "INSERT": "secondary",
    # The same red as the labels it puts up
    "FLASH": "red",
}


def mode_color(api: TodooitAPI, mode: str) -> str:
    theme = api.vars.theme
    return getattr(theme, MODE_COLORS.get(mode, "primary"))


# The mode block takes its color from the mode itself, so the two caps around it
# have to be repainted whenever it changes. A `text` widget is fixed at
# startup and can't follow along, so all three pieces are built here, each one
# its own widget listening to the same event.
def mode_widget(render: Callable[[TodooitAPI, str], Text]) -> StatusBarWidget:
    @subscribe(ModeChanged)
    def wrapper(api: TodooitAPI, event: ModeChanged) -> Text:
        return render(api, event.mode)

    return StatusBarWidget(wrapper)


def mode_cap(glyph: str) -> StatusBarWidget:
    return mode_widget(
        lambda api, mode: Text(
            glyph,
            style=Style(color=mode_color(api, mode), bgcolor=bar_background(api)),
        )
    )


def mode_label(api: TodooitAPI, mode: str) -> Text:
    return Text(
        f" {mode} ",
        style=Style(
            color=api.vars.theme.background1,
            bgcolor=mode_color(api, mode),
            bold=True,
        ),
    )


# Today, written the way every other date in the app is written. Read off the
# clock rather than out of an event: no event fires when midnight passes.
DATE_TICK = 60


def date_widget(fg: str, bg: str) -> StatusBarWidget:
    @timer(DATE_TICK)
    def today(*_) -> str:
        return day_label(date.today())

    return StatusBarWidget(today, fmt="[bold] 󰃭 {} [/]", fg=fg, bg=bg)


@subscribe(Startup)
def bar_setup(api: TodooitAPI, _):
    theme = api.vars.theme

    # The mode sits alone on the left as a pill, and the three things that say
    # where and when you are chained to the right edge: the project in front of
    # you, the time, and the day. Nothing here counts or measures the work --
    # that is what the panes are for -- so the chain stays the same width
    # whatever the todos do. It alternates between a recessed and a raised
    # background so each segment stays its own block, and ends on the accent,
    # where the eye lands last.
    bar_widgets = [
        mode_cap(ROUND_OPEN),
        mode_widget(mode_label),
        mode_cap(ROUND_CLOSE),
        spacer(width=0, bg=bar_background(api)),
        text(ROUND_OPEN, fg=theme.background3, bg=bar_background(api)),
        current_project(
            fmt=" 󰉋 {} ",
            fg=theme.foreground3,
            bg=theme.background3,
        ),
        text(ROUND_OPEN, fg=theme.background1, bg=theme.background3),
        clock(
            format="%H:%M",
            fmt=" 󰥔 {} ",
            fg=theme.foreground2,
            bg=theme.background1,
        ),
        text(ROUND_OPEN, fg=theme.primary, bg=theme.background1),
        date_widget(fg=theme.background1, bg=theme.primary),
    ]
    api.bar.set(bar_widgets)
