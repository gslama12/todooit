"""
The note editor widget: the bindings, and which key goes where
"""

from textual import events
from textual.binding import Binding

from .clipboard import ClipboardEditing
from .normal import NormalKeys


class NoteEditor(NormalKeys, ClipboardEditing):
    """
    Plain text editor that styles emphasis, quotes and bullets as typed.

    Two modes: NORMAL (read-only, letters move the cursor) and INSERT (letters
    type). `i` enters INSERT; `escape` steps back to NORMAL, then to the todo.
    Opens in NORMAL when the note has content, INSERT when empty.

    Selecting/copying/pasting work in both modes; cut/paste switch to INSERT.
    The clipboard speaks markdown: copies are written as it, pastes read as it.

    Markup is typed like markdown (`- `, `1. `, `> `, `# `, `---`, `*stars*`)
    and rendered on completion. The only keyboard-only action is nesting
    (`tab`/`shift+tab`); a quote wraps a line, so markup nests inside it too.

    Files are attached, not typed: `ctrl+v` drops one in the footer strip;
    `f` focuses it.
    """

    BINDINGS = [
        # Nesting has no markup mark, so it needs a key: `tab` only (ctrl+i is
        # the same byte on non-kitty terminals; no other widget needs it here).
        Binding("tab", "indent", "Indent", show=False),
        Binding("shift+tab", "dedent", "Unindent", show=False),
        # Overrides TextArea's delete-right; clears the whole note (after y/N).
        Binding("ctrl+d,super+d", "clear_note", "Clear the note", show=False),
        # TextArea binds this to cursor_line_start, already on `home`.
        Binding("ctrl+a,super+a", "select_all", "Select all", show=False),
        # TextArea already takes Cmd for cut/copy/undo/redo, but not paste.
        Binding("super+v", "paste", "Paste", show=False),
        # What a Mac's opt/cmd editing chords arrive as through the terminal:
        # opt+delete, shift+opt+arrows, and cmd+backspace (^U).
        Binding("alt+d", "delete_word_right", "Delete word right", show=False),
        Binding("alt+shift+left", "cursor_word_left(True)", show=False),
        Binding("alt+shift+right", "cursor_word_right(True)", show=False),
        # Overrides TextArea's delete-to-line-start: the whole line, as zsh does.
        Binding("ctrl+u", "clear_line", "Clear the line", show=False),
        # Top / bottom of the note (cmd+up/down, sent on by the terminal).
        Binding("ctrl+home", "note_start", "Top of the note", show=False),
        Binding("ctrl+end", "note_end", "Bottom of the note", show=False),
    ]

    async def _on_key(self, event: events.Key) -> None:
        """
        Handle mode-specific keys, and carry the bullet/quote prefix onto a newly opened line.
        """

        if self.host.awaiting_answer:
            # Editor keeps focus during a pending question; answer lands here, not on a screen binding.
            event.stop()
            event.prevent_default()
            self.host.answer(event.key)
            return

        # Resolved character, not raw key name, so motions on ö etc. match the trees.
        key = self.host.resolve_key(event)

        if self.read_only:
            if self._handle_normal_key(key):
                event.stop()
                event.prevent_default()

                # Restart the blink so a move mid-blink isn't hidden.
                self._restart_blink()

            # escape bubbles: with no mode left to leave, it should close the window.
            return

        if key == "escape":
            event.stop()
            event.prevent_default()
            self.enter_normal()
            return

        # A Meta chord (`alt+d`) carries its letter, which TextArea would type;
        # skip that so the key reaches its binding instead.
        if key != event.character and key.startswith("alt+"):
            event.prevent_default()
            return

        if self._handle_insert_key(event):
            event.stop()
            event.prevent_default()
            return

        await super()._on_key(event)

    def _handle_insert_key(self, event: events.Key) -> bool:
        """Handle an INSERT-mode key; True if handled, False to let it type."""

        if event.key == "enter" and self._handle_enter():
            return True

        if (
            event.key == "backspace"
            and self.selection.is_empty
            and self._handle_backspace()
        ):
            return True

        return self._render_typed(event.character)
