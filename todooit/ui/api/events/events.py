from datetime import date
from typing import Any, Callable, Literal, Optional, Union

from textual.message import Message

from todooit.api import FixedProject, Project, Todo

# A pane can show a stored project or a fixed one; events carry whichever it is.
ProjectType = Union[Project, FixedProject]

ModeType = Literal["NORMAL", "INSERT", "CONFIRM"]
NotificationType = Literal["info", "warning", "error"]


# Super event


class TodooitEvent(Message, bubble=True):
    """Base class for all events."""


# Base events


class ProjectEvent(TodooitEvent):
    """Base class for all project events."""

    def __init__(self, project: ProjectType) -> None:
        super().__init__()
        self.project = project


class TodoEvent(TodooitEvent):
    """Base class for all todo events."""

    def __init__(self, todo: Todo) -> None:
        super().__init__()
        self.todo = todo


# Events


class Startup(TodooitEvent):
    """Emitted when the app starts."""


class ShutDown(TodooitEvent):
    """Emitted when user presses the exit app keybind."""


class SpawnHelp(TodooitEvent):
    """Emitted when user presses `?` in NORMAL mode."""


class SpawnQuickAdd(TodooitEvent):
    """Emitted when the user wants to type a whole task in one line."""


class SpawnNote(TodooitEvent):
    """Emitted when user wants to see and edit the note of a todo."""

    def __init__(self, todo: Todo) -> None:
        super().__init__()
        self.todo = todo


class SpawnMove(TodooitEvent):
    """Emitted when the user wants to file a task under another project."""

    def __init__(self, todo: Todo) -> None:
        super().__init__()
        self.todo = todo


class SpawnCalendar(TodooitEvent):
    """Emitted to pick a date from a calendar; carries the tree being edited, not the field, since the screen pushes the window and routes the result back."""

    def __init__(self, tree: Any, column: str, initial: Optional[date]) -> None:
        super().__init__()
        self.tree = tree
        self.column = column
        self.initial = initial


class ModeChanged(TodooitEvent):
    """Emitted when there is a change in the `status`."""

    def __init__(self, mode: ModeType) -> None:
        super().__init__()
        self.mode: ModeType = mode


class SpawnSearch(TodooitEvent):
    """Emitted when user wants to find a task anywhere in the tree."""


class GotoFixedProject(TodooitEvent):
    """Emitted to jump straight into a fixed project; moves the projects pane there and hands focus to the tasks pane."""

    def __init__(self, key: str) -> None:
        super().__init__()
        self.key = key


class ShowConfirm(TodooitEvent):
    """Emitted when confirmation is required; the asker spells out the question and both outcome messages, since the row may be gone or off screen by the time it's answered."""

    def __init__(
        self,
        callback: Callable,
        message: str,
        confirmed: str,
        cancelled: str,
    ) -> None:
        super().__init__()
        self.callback = callback
        self.message = message
        self.confirmed = confirmed
        self.cancelled = cancelled


# Project events


class ProjectSelected(ProjectEvent):
    """Emitted when user selects a project."""

    def __init__(self, project: ProjectType) -> None:
        super().__init__(project)


# Todo events


class TodoSelected(TodoEvent):
    """Emitted when user selects a todo."""

    def __init__(self, todo: Todo) -> None:
        super().__init__(todo)


class RevealTodo(TodoEvent):
    """Emitted when a task leaves its current pane (e.g. unticked, restored from Bin) and has to be shown wherever it now lives: its pane opens, cursor moves there, row flashes."""


class BarNotification(TodooitEvent):
    """Emitted when a notification is to be displayed."""

    def __init__(
        self,
        message: str,
        level: NotificationType,
        auto_exit: bool = True,
        details: Optional[str] = None,
    ) -> None:
        super().__init__()
        self.message = message
        self.level: NotificationType = level
        self.auto_exit = auto_exit
        # Extra text an error carries onto the clipboard but not onto the
        # screen, e.g. the traceback of the exception behind it
        self.details = details


class StartFieldEdit(TodooitEvent):
    """Emitted when editing starts on a column the pane doesn't draw, so the bar shows the buffer instead (the tree still owns the edit)."""

    def __init__(self, tree: Any, column: str) -> None:
        super().__init__()
        self.tree = tree
        self.column = column


class HistoryStep(TodooitEvent):
    """Emitted to undo/redo; the screen performs the actual step since it owns the panes and a step can drop one's project."""

    def __init__(self, forward: bool) -> None:
        super().__init__()
        self.forward = forward


class QuitApp(TodooitEvent):
    """Internally used Quit Event."""
