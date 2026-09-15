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

# space kept on either side of a column, so that neighbouring columns are
# separated by twice as much as the table edges get
COLUMN_PADDING = 2

# Guides drawn to the left of a nested item, in the same rounded style the pane
# borders use: a line drops out of the parent's first column and turns right
# into the first column of each of its children, the way a file tree does.
# All four are the same width, which is what one level of nesting indents by.
GUIDE_BRANCH = "├── "
GUIDE_LAST_BRANCH = "╰── "
GUIDE_VERTICAL = "│   "
GUIDE_BLANK = "    "

# How a description too long for its column is broken. Folded, never cut
# short: a row says what there is to do, and a word of that quietly swapped
# for an ellipsis is the one word the row was worth reading for
DESCRIPTION_OVERFLOW = "fold"

# The line of GUIDE_VERTICAL with none of the gap after it. A row is drawn
# over as many lines as its description needs, and what hangs off it starts
# only on the line after the last of them: this is what carries the line down
# through the row, in the column its children turn out of.
GUIDE_DROP = GUIDE_VERTICAL[0]

# How far the guides are pulled towards the pane background. Far enough that
# they stay behind the descriptions they indent, and short of the point where
# the shape of the tree stops being readable.
GUIDE_FADE = 0.45

if TYPE_CHECKING:  # pragma: no cover
    from todooit.ui.widgets.trees.model_tree import ModelTree


class HangingText:
    """
    Text wrapping into its column, with every line after the first pushed in

    What makes room, in a pane whose first column is the description itself,
    for the line dropping out of that column into the rows under it. The
    description starts where it always did and wraps where it always did;
    only its second line onwards steps aside, into the same column the rows
    below it turn their elbows out of.
    """

    def __init__(self, text: Text, indent: int):
        self.text = text
        self.indent = indent

    def _lines(self, width: int) -> List[Text]:
        """
        The text broken to `width`, and to one indent less below its first line

        Wrapped a line at a time rather than all at once, since the first line
        has the whole column to run in and the rest have the indent taken out
        of them: one call cannot break a run of text to two different widths.
        """

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
    A row drawn in what the guides that place it in the tree leave of the pane

    The guides are a margin the whole row sits in rather than something glued
    to the front of its first cell: a description long enough to wrap would
    otherwise take its second line back to the left edge of the pane, out from
    under the row it belongs to and straight through the lines it hangs off.
    Every line of the row gets a prefix of its own — the elbow on the first,
    and below it only the ancestors whose lines carry on past the row.

    The row inside is built without the padding a table keeps at its edges,
    since the margin here is that padding: `inset` holds the same gap in front
    of the guides that an unguided row has in front of its first column, and
    `tail` the same gap after the last one, so that every row of the pane
    lines up with the column titles however deep it is nested.

    `connector` is the other line a tall row has to carry: what hangs off the
    row turns out of its own first column, which is past the margin and inside
    the row, so a row that wrapped has to be drawn through rather than around.
    `connector_offset` says how far into the row that column starts.
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
        # A column is kept back for the row itself, so that a pane narrow
        # enough to be all margin still draws something rather than raising
        width = options.max_width - self.margin - self.tail
        return options.update_width(max(width, 1))

    def _connected(self, line: List[Segment]) -> List[Segment]:
        """
        A line of the row with the drop into its own family drawn through it

        Into the gap the row leaves in that column rather than over anything
        standing there: a pane whose first column is the description itself
        has no gap to draw it in once the description has wrapped into it,
        and the line is left out rather than a letter of it painted over.
        """

        drawn: List[Segment] = []
        column = 0
        done = False

        for segment in line:
            text = segment.text
            width = segment.cell_length
            reached = column <= self.connector_offset < column + width

            # A segment holding anything double width is measured in cells
            # and cut in characters, which are not the same count in it
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

            # The first line is where the row itself is: the drop only has to
            # cross the lines under it, on its way to the row hanging off it
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

        # An editing field draws its buffer plus whatever hint it appends to it,
        # which is wider than the buffer alone: measure what actually gets drawn
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
        The file tree guides for this item: its first line, then every line below

        The innermost level is the elbow the item itself hangs off; every level
        above it only says whether the line of that ancestor carries on past
        this row or has already run out of siblings. They stop at whichever
        row the pane counts as the top of the family, which in a pane that
        gathers its rows is not the top of the tree.

        A row tall enough to have lines below its first gets the same guides
        again underneath, with its own elbow spent: what is left there is the
        line carrying on to the next row beside it, or nothing at all once
        this row is the last of them.
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
        """
        The line dropping out of this row's first column into its own family

        Something only a row drawn over more than one line ever needs: what
        hangs off a row starts on the line after the last of its own, and
        between the two there is nothing but however far it wrapped.
        """

        if not self.tree.show_guides:
            return ""

        return GUIDE_DROP if self.tree.draws_rows_under(self.model) else ""

    def _with_row_mark(self, rendered: RenderableType) -> RenderableType:
        """
        The description behind whatever the pane has to put in front of it

        In front rather than after, and inside the description's own column:
        what a mark says is what to do with the row, which is read before the
        row itself and not hunted for at the end of it.
        """

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

        # A guided row keeps its edge padding out in the margin, where the
        # guides are drawn in it; an unguided one has the table draw it
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

            # Measured on what is about to be drawn, so that a field which grows
            # while it is edited gets the column widened for it
            if self._cell_len(rendered) > self._get_max_width(attr):
                self.tree.get_column_width.cache_clear()

            # A pane's note on the row shares the description's column
            # rather than taking one of its own: pushed to the far end of it,
            # kept on one line, and left out of the width check above, since
            # it is the pane's word about the row and not the field's. What is
            # left of the column goes to the description, which wraps into it
            # exactly as it would have without a note.
            # The pane's mark on the row leads its description, edit or no
            # edit: a mark that came and went as the description was typed
            # into would shift the whole of it sideways and back again
            if attr == "description":
                rendered = self._with_row_mark(rendered)

            if attr == "description" and not component.is_editing:
                rendered = self._with_row_note(rendered)

            # A pane whose description is its first column has the line into
            # the rows below coming down through that column. Only a row with
            # rows under it has such a line, and only that row hangs its
            # description in to leave a column free for it: the rest wrap
            # flush, since there would be nothing to put in the gap
            if attr == "description" and index == 0 and connector:
                if isinstance(rendered, Text):
                    rendered = HangingText(rendered, len(GUIDE_VERTICAL))

            if attr == "description":
                table.add_column(attr, ratio=1, overflow=DESCRIPTION_OVERFLOW)
            else:
                width = self._get_max_width(attr)

                # the leftmost column has to hold the table edge padding as
                # well, unless the margin is already holding it
                if index == 0 and not guided:
                    width += COLUMN_PADDING

                table.add_column(attr, width=width)

            row.append(rendered)

        table.add_row(*row)

        if not guided and not connector:
            return table

        # The guides are what pushes a nested row to the right: the row is
        # drawn in what is left of the pane beside them, every line of it. A
        # row deep enough to have guides has its own first column where they
        # end; one at the top of the tree has it past the pane's edge gap,
        # which the table is still drawing itself in that case
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
        # A field that rejects what was typed raises out of here, and the tree
        # turns that into a notification. The edit still has to be torn down on
        # the way out, or the tree keeps routing keystrokes into the buffer
        # while the bar claims to be back in NORMAL mode
        try:
            getattr(self, self.editing).stop_edit(cancel)
        finally:
            self.tree.get_column_width.cache_clear()
            self.editing = ""

    def handle_keypress(self, key: str) -> bool:
        getattr(self, self.editing).keypress(key)
        return True
