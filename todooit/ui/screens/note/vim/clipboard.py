"""
Copy, cut and paste: the clipboard speaks markdown, as the note itself does
"""

from textual import events

from todooit.utils import (
    copy_text,
    find_links,
    looks_like_path,
    paste_files,
    paste_text,
)
from todooit.utils.links import TITLE_MAX as LINK_TITLE_MAX

from ..disp.markdown import (
    PASTE_BLOCK,
    PASTE_INLINE,
    PASTE_STRIP,
    from_markdown,
)
from ..disp.markup import RULE_RE, line_prefix
from .editing import TextEditing

# Brackets can't appear in a link name - they mark where the name stops
NO_BRACKETS = str.maketrans("", "", "[]")


def pasted_paths(text: str) -> list:
    """Paths a paste consists of, one per line; [] unless every line is a path."""

    lines = [line.strip().strip("\"'").strip() for line in text.splitlines()]
    lines = [line for line in lines if line]

    if not lines or not all(looks_like_path(line) for line in lines):
        return []

    return lines


def pasted_link(text: str):
    """The link a paste consists of, if it's one link long enough to be worth naming; None otherwise."""

    stripped = text.strip()
    links = find_links(stripped)

    if len(links) != 1:
        return None

    link = links[0]

    if link.title or (link.start, link.end) != (0, len(stripped)):
        return None

    return link if len(stripped) > LINK_TITLE_MAX else None


class ClipboardEditing(TextEditing):
    """Selecting/copying/pasting work in both modes; cut/paste switch to INSERT."""

    def action_copy(self) -> None:
        """
        Copy the selection, or the whole note if none (overrides TextArea, which does nothing without a selection), as stored.
        """

        copy_text(self.app, self.selected_text or self.text)

    def action_paste(self) -> None:
        """
        Drop the system clipboard in at the cursor (overrides TextArea, which only reads its own internal clipboard). Switches to INSERT, since pasting is an edit.
        """

        text = paste_text(self.app)

        # A file-manager copy puts nothing on the text clipboard, so check paste_files() too.
        paths = pasted_paths(text) if text else paste_files()

        if paths:
            # Files are attached to the note, not written into it.
            self.host.attach(paths)
            return

        if text:
            self._paste(text)

    async def _on_paste(self, event: events.Paste) -> None:
        """
        The terminal's own paste (how Windows Terminal sends ctrl+v and right-click), handled like `action_paste` rather than TextArea's verbatim insert - which also drops it in NORMAL.
        """

        event.stop()
        event.prevent_default()

        if (
            self.host.awaiting_answer
            or self.search_prompt is not None
            or not event.text
        ):
            return

        if paths := pasted_paths(event.text):
            self.host.attach(paths)
            return

        self._paste(event.text)

    def _paste(self, text: str) -> None:
        """
        Write pasted text in at the cursor: a bare URL as a link, anything else read as markdown.
        """

        self.enter_insert()

        if self._paste_as_link(text):
            return

        self._paste_markdown(text)

    def _paste_markdown(self, text: str) -> None:
        """
        Write pasted markdown in as the markup typing it would have produced, then number any list it landed in.
        """

        start, end = sorted(self.selection)
        row, column = start

        line = self.document[row]
        before = line[:column]

        # Line-start markup only means something where a line starts; right
        # after a marker it would be a second one, so it's dropped
        if not before:
            first = PASTE_BLOCK
        elif before == line_prefix(line):
            first = PASTE_STRIP
        else:
            first = PASTE_INLINE

        above = self._stored_line(row - 1) if row > 0 else ""
        converted = from_markdown(text, first, above)

        # A pasted rule would swallow the words after the cursor (and stop being a rule)
        after = self.document[end[0]][end[1] :]

        if after and RULE_RE.match(converted.rsplit("\n", 1)[-1]):
            converted += "\n"

        self._replace_via_keyboard(converted, start, end)

    def _paste_as_link(self, text: str) -> bool:
        """
        Insert a pasted URL as a markdown link; False if the paste wasn't a bare URL. The current selection, if any, becomes the link's title.
        """

        link = pasted_link(text)

        if link is None:
            return False

        # Collapse to one line; strip brackets, which would close the markdown link early.
        title = " ".join(self.selected_text.split()).translate(NO_BRACKETS)
        markdown = f"[{title}]({link.url})"

        self._replace_via_keyboard(markdown, *self.selection)

        return True

    def action_cut(self) -> None:
        """
        Cut the selection to the clipboard (overrides TextArea for the same reason as `copy`); switches to INSERT like `paste`.
        """

        start, _ = self.selection
        removed = self.selected_text or self._stored_line(start[0])

        self.enter_insert()
        super().action_cut()

        copy_text(self.app, removed)
