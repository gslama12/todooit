"""
Flash mode (`t`, "to"): every row on screen in the focused pane gets a label at its
left edge, and typing a label puts the cursor on that row.

Kept to the rows that are actually on screen, like flash.nvim / easymotion:
the labels are for picking a row you can see, not for searching. While it is
on, every key goes here instead of the keybindings, so the label letters can
overlap the motion keys without either getting in the other's way.
"""

from typing import Dict, List, Optional

from rich.segment import Segment
from rich.style import Style as RichStyle
from textual import events, on
from textual.color import Color
from textual.filter import dim_color
from textual.strip import Strip

from todooit.ui.api.events import ModeChanged

from .base_tree import BaseTree

# Nearest rows get the easiest keys: the home row first (qwertz, as the pane
# keys are), then the rest of the letters. The default for
# `api.vars.flash_alphabet`, which a config can change
FLASH_ALPHABET = "asdfghjklöqwertzuiopyxcvbnm"

# How far a row's text is pulled towards its background while labels are up
FLASH_DIM = 0.5


def flash_labels(count: int, alphabet: str = FLASH_ALPHABET) -> List[str]:
    """
    Labels for `count` rows, top to bottom. All one key while the alphabet is
    enough, otherwise all two: mixing the two would leave the letters that
    start a pair unusable as labels of their own.
    """

    if count <= len(alphabet):
        return list(alphabet[:count])

    pairs = [first + second for first in alphabet for second in alphabet]
    return pairs[:count]


class FlashJump(BaseTree):
    """The flash-mode half of a pane: its labels, the keys typed into them, and drawing them."""

    def __init__(self, *args, **kwargs) -> None:
        super().__init__(*args, **kwargs)

        # label -> option index, for as long as the labels are up
        self._flash_labels: Dict[str, int] = {}

        # The first key of a two-key label, once typed
        self._flash_typed = ""

    @property
    def is_flashing(self) -> bool:
        return bool(self._flash_labels)

    def visible_row_indices(self) -> List[int]:
        """The option indices of the rows whose first line is on screen, top to bottom, skipping headings and rules."""

        top = self.scroll_offset.y
        bottom = top + self.scrollable_content_region.height
        lines = self._lines

        return [
            index
            for index, offset in lines[top:bottom]
            if offset == 0 and not self._options[index].disabled
        ]

    def start_flash(self) -> bool:
        """Puts a label on every row on screen; False (and nothing changes) if there are none."""

        rows = self.visible_row_indices()
        if not rows:
            return False

        alphabet = self.api.vars.flash_alphabet
        self._flash_labels = dict(zip(flash_labels(len(rows), alphabet), rows))
        self._flash_typed = ""
        self.app.post_message(ModeChanged("FLASH"))
        self.refresh()

        return True

    def cancel_flash(self) -> None:
        """Takes the labels down without moving; a no-op when none are up."""

        if not self.is_flashing:
            return

        self._flash_labels = {}
        self._flash_typed = ""
        self.app.post_message(ModeChanged("NORMAL"))
        self.refresh()

    def handle_flash_key(self, key: str) -> None:
        """
        One key typed while the labels are up. A whole label jumps, the first
        key of a pair waits for the second (backspace takes it back), and
        anything else -- escape included -- cancels and is used up.
        """

        if key == "backspace" and self._flash_typed:
            self._flash_typed = ""
            self.refresh()
            return

        typed = self._flash_typed + key
        index = self._flash_labels.get(typed)

        if index is not None:
            self.cancel_flash()
            self.highlighted = index
            return

        if len(key) == 1 and any(label.startswith(typed) for label in self._flash_labels):
            self._flash_typed = typed
            self.refresh()
            return

        self.cancel_flash()

    # The rows move under the labels, so they no longer point where they say
    @on(events.Resize)
    def _cancel_flash_on_resize(self, _: events.Resize) -> None:
        self.cancel_flash()

    @on(events.Blur)
    def _cancel_flash_on_blur(self, _: events.Blur) -> None:
        self.cancel_flash()

    def _flash_label_at(self, index: int) -> Optional[str]:
        """The label drawn on the row at `index`, or None if it gets none (or lost it to the key typed)."""

        for label, at in self._flash_labels.items():
            if at == index:
                return label if label.startswith(self._flash_typed) else None

        return None

    def _flash_strip(self, strip: Strip, label: Optional[str]) -> Strip:
        """A row's line with its text dimmed and, if it has one, its label over the left edge."""

        theme = self.api.vars.theme
        background = Color.parse(theme.background1).rich_color

        def dim(style: Optional[RichStyle]) -> Optional[RichStyle]:
            if style is None or style.color is None:
                return style

            under = style.bgcolor or background
            return style + RichStyle(color=dim_color(under, style.color, FLASH_DIM))

        dimmed = Strip(
            [Segment(segment.text, dim(segment.style)) for segment in strip],
            strip.cell_length,
        )

        if not label:
            return dimmed

        # On whatever the row sits on (the cursor's bar included), so only the
        # letters stand out
        first = next(iter(strip), None)
        base = RichStyle(bgcolor=first.style.bgcolor) if first and first.style else RichStyle()

        red = Color.parse(theme.red)
        typed = len(self._flash_typed)
        label_strip = Strip(
            [
                # The key already typed of a pair, faded, so the one left to type leads
                Segment(
                    label[:typed],
                    base + RichStyle(color=red.blend(Color.parse(theme.background1), FLASH_DIM).rich_color, bold=True),
                ),
                Segment(label[typed:], base + RichStyle(color=red.rich_color, bold=True)),
            ],
            len(label),
        )

        return Strip.join([label_strip, dimmed.crop(len(label), strip.cell_length)])

    def render_line(self, y: int) -> Strip:
        strip = super().render_line(y)

        if not self.is_flashing:
            return strip

        try:
            index, offset = self._lines[self.scroll_offset.y + y]
        except IndexError:
            return strip

        label = self._flash_label_at(index) if offset == 0 else None
        return self._flash_strip(strip, label)
