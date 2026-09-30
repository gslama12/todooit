from typing import TYPE_CHECKING, Generic, List, Tuple, TypeVar, Union
from rich._wrap import divide_line
from rich.cells import cell_len
from rich.console import Console, ConsoleOptions, RenderableType, RenderResult
from rich.measure import Measurement
from rich.segment import Segment
from rich.style import Style
from rich.table import Table
from rich.text import Text
from todooit.api import Todo, Project
from todooit.utils import blend
from ..inputs.simple_input import SimpleInput

ModelType = TypeVar("ModelType", bound=Union[Todo, Project])

# Padding on each side of a column; neighbouring columns get double this.
COLUMN_PADDING = 2

# File-tree-style guides drawn left of a nested item, all the same width
# (one level of indent).
GUIDE_BRANCH = "├── "
GUIDE_LAST_BRANCH = "╰── "
GUIDE_VERTICAL = "│   "
GUIDE_BLANK = "    "

# Folded rather than cut short, so overflow keeps whole words.
DESCRIPTION_OVERFLOW = "fold"

# GUIDE_VERTICAL without its trailing gap: carries the line down through a
# wrapped row to the column its children turn out of.
GUIDE_DROP = GUIDE_VERTICAL[0]

# How far guides are faded towards the pane background (still readable, but
# behind the text they indent).
GUIDE_FADE = 0.45

if TYPE_CHECKING:  # pragma: no cover
    from todooit.ui.widgets.trees.model_tree import ModelTree


class HangingText:
    """
    Text wrapped into its column with every line after the first indented,
    to leave room for the guide line dropping into the rows below.
    """

    def __init__(self, text: Text, indent: int):
        self.text = text
        self.indent = indent

    def _lines(self, width: int) -> List[Text]:
        """Text broken to `width`; first line full width, rest narrowed by indent (wrapped one line at a time, since a call can't break to two widths)."""

        first = max(width, 1)
        rest = max(width - self.indent, 1)

        lines: List[Text] = []
        remaining = self.text.copy()
        available = first

        while True:
            offsets = divide_line(remaining.plain, available, fold=True)

            if not offsets or offsets[0] <= 0:
                remaining.rstrip_end(available)
                lines.append(remaining)
                return lines

            line = remaining[: offsets[0]]
            line.rstrip_end(available)
            lines.append(line)

            remaining = remaining[offsets[0] :]
            available = rest

    def __rich_console__(
        self, console: Console, options: ConsoleOptions
    ) -> RenderResult:
        lines = self._lines(options.max_width)
        pad = Text(" " * self.indent)

        yield from (
            Text("\n")
            .join(line if not index else pad + line for index, line in enumerate(lines))
            .render(console)
        )

    def __rich_measure__(
        self, console: Console, options: ConsoleOptions
    ) -> Measurement:
        inner = Measurement.get(console, options, self.text)

        # However narrow the column gets, the indent still has to fit in it
        return Measurement(
            min(inner.minimum + self.indent, inner.maximum), inner.maximum
        )


class GuidedRow:
    """
    A row drawn beside its tree guides, which form a margin (not a prefix on
    the first cell) so wrapped description lines stay indented instead of
    reaching the pane's left edge. `inset`/`tail` replace the table's own
    edge padding; `connector`/`connector_offset` draw the line to this row's
    children through the row when it has wrapped.
    """

    def __init__(
        self,
        first: str,
        rest: str,
        style: Style,
        row: RenderableType,
        inset: int = 0,
        tail: int = 0,
        connector: str = "",
        connector_offset: int = 0,
    ):
        self.first = first
        self.rest = rest
        self.style = style
        self.row = row
        self.inset = inset
        self.tail = tail
        self.connector = connector
        self.connector_offset = connector_offset

    @property
    def margin(self) -> int:
        return self.inset + cell_len(self.first)

    def _inner_options(self, options: ConsoleOptions) -> ConsoleOptions:
        # Clamp to 1 so an overly narrow pane still draws instead of raising.
        width = options.max_width - self.margin - self.tail
        return options.update_width(max(width, 1))

    def _connected(self, line: List[Segment]) -> List[Segment]:
        """
        A line of the row with the connector to its children drawn through it,
        into whatever gap the row happens to leave in that column (never over
        existing text).
        """

        drawn: List[Segment] = []
        column = 0
        done = False

        for segment in line:
            text = segment.text
            width = segment.cell_length
            reached = column <= self.connector_offset < column + width

            # Skip double-width segments: cell length and character count differ.
            if done or not reached or len(text) != width:
                drawn.append(segment)
                column += width
                continue

            at = self.connector_offset - column
            column += width

            if text[at] != " ":
                drawn.append(segment)
                continue

            style = self.style if segment.style is None else segment.style + self.style

            for piece, piece_style in (
                (text[:at], segment.style),
                (self.connector, style),
                (text[at + 1 :], segment.style),
            ):
                if piece:
                    drawn.append(Segment(piece, piece_style))

            done = True

        return drawn

    def __rich_console__(
        self, console: Console, options: ConsoleOptions
    ) -> RenderResult:
        lines = console.render_lines(self.row, self._inner_options(options), pad=True)
        lead = " " * self.inset

        for index, line in enumerate(lines):
            yield Segment(lead + (self.first if index == 0 else self.rest), self.style)

            # Connector only applies below the first line (the row's own line).
            yield from self._connected(line) if index and self.connector else line

            if self.tail:
                yield Segment(" " * self.tail)

            yield Segment.line()

    def __rich_measure__(
        self, console: Console, options: ConsoleOptions
    ) -> Measurement:
        inner = Measurement.get(console, self._inner_options(options), self.row)
        around = self.margin + self.tail

        return Measurement(inner.minimum + around, inner.maximum + around)


class BaseRenderer(Generic[ModelType]):
    editing: str = ""

    def __init__(self, model: ModelType, tree: "ModelTree"):
        self._model = model
        self.tree = tree
        self.post_init()

    def post_init(self):  # pragma: no cover
        pass

    def _get_component(self, component: str) -> SimpleInput:
        return getattr(self, component)

    @property
    def id(self) -> str:
        return self._model.uuid

    @property
    def table_layout(self) -> List:
        return self.tree.render_layout

    @property
    def prompt(self) -> RenderableType:
        return self.make_renderable()

    @property
    def model(self) -> ModelType:
        raise NotImplementedError  # pragma: no cover

    def _cell_len(self, rendered) -> int:
        return rendered.cell_len if isinstance(rendered, Text) else len(rendered)

    def _get_attr_width(self, attr: str) -> int:
        component = self._get_component(attr)
        formatter = self.tree.formatter
        rendered: str = getattr(formatter, attr).format_value(
            self.tree.column_value(attr, component), component.model
        )

        # Measure what's actually drawn: an editing field's hint widens it
        # beyond just the buffer.
        if component.is_editing:
            editing_width = self._cell_len(component.render_editing(self.theme))
        else:
            editing_width = len(component.value) + 1

        return max(editing_width, len(rendered))

    def _get_max_width(self, attr: str) -> int:
        return self.tree.get_column_width(attr)

    @property
    def theme(self):
        return self.tree.api.vars.theme

    @property
    def guide_style(self) -> Style:
        theme = self.theme
        return Style(color=blend(theme.foreground1, theme.background1, GUIDE_FADE))

    @property
    def tree_guides(self) -> Tuple[str, str]:
        """
        File-tree guides for this item: (first line, every line below).

        The innermost level is this item's own elbow; ancestors above it just
        say whether their line continues past this row or ran out of
        siblings. Stops at the pane's row root, not necessarily the tree root.
        """

        if not self.tree.show_guides:
            return "", ""

        node = self.model
        pieces: List[str] = []
        last_here = True

        while node.nest_level and not self.tree.is_row_root(node):
            last = self.tree.is_last_row(node)

            if pieces:
                pieces.append(GUIDE_BLANK if last else GUIDE_VERTICAL)
            else:
                last_here = last
                pieces.append(GUIDE_LAST_BRANCH if last else GUIDE_BRANCH)

            node = node.parent

        if not pieces:
            return "", ""

        pieces.reverse()
        below = pieces[:-1] + [GUIDE_BLANK if last_here else GUIDE_VERTICAL]

        return "".join(pieces), "".join(below)

    @property
    def child_connector(self) -> str:
        """Guide line from this row's first column down to its children, if any."""

        if not self.tree.show_guides:
            return ""

        return GUIDE_DROP if self.tree.draws_rows_under(self.model) else ""

    def _with_row_mark(self, rendered: RenderableType) -> RenderableType:
        """Prefix a pane's mark onto the description, so it reads before the row."""

        mark = self.tree.row_mark(self.model)

        if not mark.cell_len:
            return rendered

        return mark + rendered if isinstance(rendered, Text) else rendered

    def _with_row_note(self, rendered: RenderableType) -> RenderableType:
        """
        The description with whatever the pane has to say about the row after it
        """

        note = self.tree.row_note(self.model)

        if not note.cell_len:
            return rendered

        cell = Table.grid(expand=True)
        cell.add_column(ratio=1)
        cell.add_column(justify="right", no_wrap=True, width=note.cell_len)
        cell.add_row(rendered, note)

        return cell

    def make_renderable(self) -> RenderableType:
        layout = self.table_layout

        first_guide, below_guide = self.tree_guides
        guided = bool(first_guide)
        connector = self.child_connector

        # A guided row's edge padding lives in the margin instead; the table
        # only draws it for unguided rows.
        table = Table.grid(
            expand=True, padding=(0, COLUMN_PADDING), pad_edge=not guided
        )
        row = []

        for index, item in enumerate(layout):
            attr = item.value
            component = self._get_component(attr)

            if component.is_editing:
                rendered = component.render_editing(self.theme)
            else:
                formatter = self.tree.formatter
                rendered = getattr(formatter, attr).format_value(
                    self.tree.column_value(attr, component), component.model
                )

            # Measure what's about to be drawn, so a field that grows while
            # edited gets its column widened.
            if self._cell_len(rendered) > self._get_max_width(attr):
                self.tree.get_column_width.cache_clear()

            # Mark always applies (even while editing) so it doesn't appear
            # and disappear as the description is typed, shifting it sideways.
            if attr == "description":
                rendered = self._with_row_mark(rendered)

            # Note shares the description's column, pushed to its far end,
            # and is excluded from the width check above since it's the
            # pane's addition, not the field's.
            if attr == "description" and not component.is_editing:
                rendered = self._with_row_note(rendered)

            # Only a row with children hangs its description in (leaving a
            # column for the guide line down to them); others wrap flush.
            if attr == "description" and index == 0 and connector:
                if isinstance(rendered, Text):
                    rendered = HangingText(rendered, len(GUIDE_VERTICAL))

            if attr == "description":
                table.add_column(attr, ratio=1, overflow=DESCRIPTION_OVERFLOW)
            else:
                width = self._get_max_width(attr)

                # Leftmost column needs the edge padding too, unless the margin holds it.
                if index == 0 and not guided:
                    width += COLUMN_PADDING

                table.add_column(attr, width=width)

            row.append(rendered)

        table.add_row(*row)

        if not guided and not connector:
            return table

        # Unguided top-of-tree rows still need the table's own edge gap
        # accounted for via connector_offset.
        return GuidedRow(
            first_guide,
            below_guide,
            self.guide_style,
            table,
            inset=COLUMN_PADDING if guided else 0,
            tail=COLUMN_PADDING if guided else 0,
            connector=connector,
            connector_offset=0 if guided else COLUMN_PADDING,
        )

    def start_edit(self, param: str) -> bool:
        if not hasattr(self, param):
            return False

        component = self._get_component(param)
        if not component.editable:
            return False

        component.start_edit()
        self.editing = param
        return True

    def stop_edit(self, cancel: bool = False):
        """Ends the edit; returns the lifecycle's outcome, if the column has one"""

        # A rejected value raises here (tree turns it into a notification);
        # still tear down the edit state, or keystrokes keep routing to the
        # buffer while the bar thinks it's back in NORMAL mode.
        try:
            return getattr(self, self.editing).stop_edit(cancel)
        finally:
            self.tree.get_column_width.cache_clear()
            self.editing = ""

    def handle_keypress(self, key: str) -> bool:
        getattr(self, self.editing).keypress(key)
        return True
