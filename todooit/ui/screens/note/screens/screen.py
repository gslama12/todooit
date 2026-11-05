"""
The note window: a todo's note (or the pinned note) with its attachments
"""

from typing import Callable, Optional, Tuple

from rich.markup import escape
from textual import on
from textual.app import ComposeResult
from textual.containers import Vertical
from textual.timer import Timer
from textual.widgets import Static, TextArea

from todooit.api import Todo
from todooit.utils import (
    Opened,
    link_label,
    open_path,
    open_url,
    read_attachments,
    resolve_path,
    write_attachments,
)
from todooit.utils.links import drawn_column

from ...base import BaseScreen
from ..disp.theme import THEME_NAME, build_theme
from ..vim.editor import NoteEditor
from ..vim.modes import MODE_INSERT, MODE_NORMAL
from .attachments import AttachmentStrip

# How long the editor sits still before the note is written back
SAVE_DEBOUNCE = 0.4

# How long a message stands in the hint line before the hints come back
REPORT_TIMEOUT = 3

# How much of the todo's description the window title carries
TITLE_MAX = 60

class NoteFrame(Vertical):
    """
    The window itself: the text, and the files along the bottom of it. Border,
    title and mode chip live here (not on the editor) so the file strip sits
    inside the frame, lit on the note's own background.
    """

    DEFAULT_CSS = """
    NoteFrame {
        & > NoteEditor {
            height: 1fr;
        }
    }
    """


class NoteScreenBase(BaseScreen):
    """
    A note in a window over the whole screen: the two modes, the save
    debounce and the y/N clear prompt. Subclasses supply the title and where
    the text/attachments are read from and written to.
    """

    DEFAULT_CSS = """
    NoteScreenBase {
        align: center middle;

        & > NoteFrame {
            width: 80%;
            height: 85%;
        }

        & > #note-hint {
            width: 80%;
            padding: 0 2;
        }
    }
    """

    BINDINGS = [
        ("escape", "close", "Close the note"),
    ]

    # One line of hints per mode; keys that would do nothing here are omitted.
    # `{move}` is filled in with the panes' direction keys (see `hint_for`).
    HINTS = {
        MODE_NORMAL: (
            "i insert    {move} move    ud half page    o link    f files    "
            "ctrl+c copy    ctrl+d clear    esc close"
        ),
        # Markup marks, not keys to press. Kept to 80 columns (usual terminal
        # width) so a wrap doesn't split a mark from its meaning.
        MODE_INSERT: (
            "- bullet  1. list  > quote  # head  --- rule  *emph*  "
            "tab nest  esc normal"
        ),
    }

    # Hint line for when the strip (not the text) has the keyboard
    FILES_HINT = "{move} pick    enter open    xx detach    esc back to the note"

    # Worded/escaped like todooit's other delete-confirm prompts
    CLEAR_PROMPT = r"Clear the whole note? \[y/N]"

    # Offered when a file's attachment target has been moved or deleted
    GONE_PROMPT = r"{name} is gone. Detach it? \[y/N]"

    def __init__(self, at: Optional[Tuple[int, int]] = None) -> None:
        super().__init__()

        # Cursor start, as (row, column) in the stored note; None = top
        self._at = at

        self._save_timer: Optional[Timer] = None
        self._report_timer: Optional[Timer] = None

        # The action a `y` answer would run; None when no question is up
        self._question: Optional[Callable[[], None]] = None

        # Set by the first `x` of an `xx` detach in the strip
        self._pending_x = False

    @property
    def title_text(self) -> str:
        """What the window is called, written into its top border."""

        raise NotImplementedError  # pragma: no cover

    def load_note(self) -> str:
        """The text the window opens on."""

        raise NotImplementedError  # pragma: no cover

    def store_note(self, text: str) -> None:
        """
        Write the text back. Called on the debounce and again on close, so
        may be handed the same text more than once.
        """

        raise NotImplementedError  # pragma: no cover

    @property
    def frame(self) -> NoteFrame:
        return self.query_one(NoteFrame)

    @property
    def editor(self) -> NoteEditor:
        return self.query_one(NoteEditor)

    @property
    def hint(self) -> Static:
        return self.query_one("#note-hint", Static)

    @property
    def awaiting_answer(self) -> bool:
        return self._question is not None

    def load_attachments(self) -> str:
        """The files this note carries, as stored: one path per line."""

        raise NotImplementedError  # pragma: no cover

    def store_attachments(self, text: str) -> None:
        """Write them back; not debounced, unlike the note text."""

        raise NotImplementedError  # pragma: no cover

    @property
    def files(self) -> AttachmentStrip:
        return self.query_one(AttachmentStrip)

    @property
    def picking_files(self) -> bool:
        return self.files.has_the_keyboard

    def compose(self) -> ComposeResult:
        editor = NoteEditor(self.load_note())

        frame = NoteFrame()
        frame.border_title = self.title_text

        with frame:
            yield editor
            yield AttachmentStrip()

        yield Static(self.hint_for(editor.mode), id="note-hint")

    def on_mount(self) -> None:
        editor = self.editor
        editor.register_theme(build_theme(self.api.vars.theme))
        editor.theme = THEME_NAME

        self.files.show(read_attachments(self.load_attachments()), self.api.vars.theme)

        editor.focus()
        self.mode_changed()

        if self._at is not None:
            # Deferred until the window has a size to scroll within
            self.call_after_refresh(self.go_to, *self._at)

    def go_to(self, row: int, column: int) -> None:
        """
        Put the cursor at a place in the note, scrolled to the middle.
        `column` is a stored-note column, which may be inside a link's address:
        the row goes raw first, so that column is there to land on.
        """

        document = self.editor.document
        row = max(0, min(row, document.line_count - 1))

        self.editor.move_cursor((row, 0))

        column = drawn_column(document.stored_line(row), column, raw=True)

        self.editor.move_cursor((row, column), center=True)

    def hint_for(self, mode: str, picking_files: bool = False) -> str:
        """The hint line for `mode`, or for the strip while it has the keyboard."""

        motions = self.api.motion_keys()
        hint = self.FILES_HINT if picking_files else self.HINTS[mode]

        return hint.replace(
            "{move}", f"{motions.left}{motions.right}/{motions.up}{motions.down}"
        )

    def mode_changed(self) -> None:
        """Redraw the mode chip in the border and the hint line under it."""

        mode = self.editor.mode

        frame = self.frame

        frame.border_subtitle = f" {mode} "
        frame.set_class(mode == MODE_INSERT, "-insert")

        # A pending question outranks the hints; answering restores them
        if not self.awaiting_answer:
            self.hint.update(self.hint_for(mode, self.picking_files))

    def report(self, message: str) -> None:
        """
        Show `message` in the hint line, restoring the hints after a timeout -
        todooit's normal message bar is on the screen underneath this one.
        """

        if self._report_timer is not None:
            self._report_timer.stop()

        self.hint.update(message)
        self._report_timer = self.set_timer(REPORT_TIMEOUT, self.mode_changed)

    def open_link(self, url: str) -> None:
        """Hand a URL to the browser, reporting which one went (or failed)."""

        if open_url(url):
            self.report(f"Opening {link_label(url)}")
        else:
            self.report("Found no browser to open the link with")

    # ------------------------------------------------------------------
    # ------------------------- The files ------------------------------
    # ------------------------------------------------------------------

    def attach(self, paths) -> None:
        """
        Put files in the strip, reporting which went in. Only the path is
        kept - the file itself is never copied, moved or read.
        """

        held = list(self.files.paths)
        fresh = []

        for raw in paths:
            path = resolve_path(str(raw))

            if path is None or path in held:
                continue

            held.append(path)
            fresh.append(path)

        if not fresh:
            self.report("Already attached")
            return

        self._write(held)

        # Stand on the newest attachment so it can be opened immediately
        self.files.picked = len(held) - 1
        self.report(
            f"Attached {fresh[0].name}"
            if len(fresh) == 1
            else f"Attached {len(fresh)} files"
        )

    def _write(self, paths) -> None:
        """Update the strip and the database at once."""

        self.files.show(paths, self.api.vars.theme)
        self.store_attachments(write_attachments(paths))

    def pick_files(self) -> None:
        """Hand the keyboard to the strip, where a file can be picked out."""

        if not self.files.paths:
            self.report("Nothing attached")
            return

        self.files.focus()

    def leave_files(self) -> None:
        """Hand the keyboard back to the text, cursor unchanged."""

        self.editor.focus()

    def file_key(self, key: str) -> None:
        """
        A key pressed in the strip: motion keys from the panes behind this
        window, `xx` to detach, `enter`/`o` to open.
        """

        strip = self.files
        motions = self.api.motion_keys()
        pending_x, self._pending_x = self._pending_x, False

        if key == "x":
            if pending_x:
                self.detach()
            else:
                self._pending_x = True
        elif key in (motions.left, "b"):
            strip.picked = max(0, strip.picked - 1)
            strip.refresh_strip()
        elif key in (motions.right, "w"):
            strip.picked = min(len(strip.paths) - 1, strip.picked + 1)
            strip.refresh_strip()
        elif key == "0":
            strip.picked = 0
            strip.refresh_strip()
        elif key == "$":
            strip.picked = len(strip.paths) - 1
            strip.refresh_strip()
        elif key in (motions.up, motions.down):
            # Up off the top row goes back into the text above the strip
            if strip.step_row(-1 if key == motions.up else 1):
                strip.refresh_strip()
            elif key == motions.up:
                self.leave_files()
        elif key in ("enter", "o"):
            self.open_file()
        elif key in ("escape", "f", "i"):
            self.leave_files()

    def open_file(self) -> None:
        """Open the file the strip is standing on, reporting the outcome."""

        path = self.files.current

        if path is None:
            return

        outcome = open_path(path)

        if outcome is Opened.OK:
            self.report(f"Opening {path.name}")
        elif outcome is Opened.MISSING:
            self.ask(self.GONE_PROMPT.format(name=escape(path.name)), self.detach)
        else:
            self.report("Found nothing to open it with")

    def detach(self) -> None:
        """
        Remove the current file; not undoable, but the file itself is
        untouched - only the reference is dropped.
        """

        path = self.files.current

        if path is None:
            return

        kept = [held for held in self.files.paths if held != path]

        self._write(kept)
        self.report(f"Detached {path.name}")

        if not kept:
            self.leave_files()

    @on(TextArea.Changed)
    def schedule_save(self, _: TextArea.Changed) -> None:
        if self._save_timer is not None:
            self._save_timer.stop()

        self._save_timer = self.set_timer(SAVE_DEBOUNCE, self.save)

    def save(self) -> None:
        self._save_timer = None
        self.store_note(self.editor.text)

    def ask(self, prompt: str, answered: Callable[[], None]) -> None:
        """Put a question up in place of the hint line; one at a time, answered by the next keystroke."""

        if self.awaiting_answer:
            return

        self._question = answered
        self.hint.update(prompt)
        self.hint.add_class("confirming")

    def answer(self, key: str) -> None:
        """Run the pending question's action on `y`; anything else cancels it."""

        answered, self._question = self._question, None
        self.hint.remove_class("confirming")
        self.mode_changed()

        if key.lower() == "y" and answered is not None:
            answered()

    def request_clear(self) -> None:
        """Offer to throw the whole note away."""

        if not self.editor.text:
            return

        self.ask(self.CLEAR_PROMPT, self._clear)

    def _clear(self) -> None:
        self.editor.clear()

        # Save immediately rather than waiting for the debounce, so the row
        # behind the window is already up to date when it closes
        self.save()

    def action_close(self) -> None:
        if self._save_timer is not None:
            self._save_timer.stop()

        if self._report_timer is not None:
            self._report_timer.stop()

        # Save now too, in case the debounce hadn't fired yet
        self.save()

        # `dismiss`, not `pop_screen`: popping would skip the screen's push
        # callback, which is what redraws the row's note icon
        self.dismiss()


class NoteScreen(NoteScreenBase):
    """The note of one todo."""

    def __init__(self, todo: Todo, at: Optional[Tuple[int, int]] = None) -> None:
        super().__init__(at)
        self.todo = todo

    @property
    def title_text(self) -> str:
        """The todo's description, truncated to `TITLE_MAX`."""

        description = self.todo.description.strip() or "Note"

        if len(description) > TITLE_MAX:
            description = description[: TITLE_MAX - 1] + "…"

        return description

    def load_note(self) -> str:
        return self.todo.note or ""

    def load_attachments(self) -> str:
        return self.todo.attachments or ""

    def store_attachments(self, text: str) -> None:
        if self.todo.attachments == text:
            return

        self.todo.attachments = text
        self.todo.save()

    def store_note(self, text: str) -> None:
        if self.todo.note == text:
            return

        self.todo.note = text
        self.todo.save()
