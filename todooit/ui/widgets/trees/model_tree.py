from contextlib import suppress
from datetime import date
from functools import cache
from traceback import format_exc
from typing import (
    TYPE_CHECKING,
    Any,
    Callable,
    Dict,
    Generic,
    Iterable,
    List,
    Optional,
    Tuple,
    TypeVar,
    Union,
    cast,
)

from rich.cells import cell_len
from rich.console import Console, ConsoleOptions, Group, RenderableType, RenderResult
from rich.markup import escape
from rich.measure import Measurement
from rich.segment import Segment
from rich.table import Table
from rich.text import Text
from textual import events, on
from textual.app import ComposeResult
from textual.color import Color
from textual.geometry import Offset
from textual.strip import Strip
from textual.style import Style
from textual.timer import Timer
from textual.widgets import Label
from textual.widgets.option_list import Option, OptionDoesNotExist

from todooit.api import Project, Todo
from todooit.api.expansion import is_expanded, set_expanded
from todooit.api.lifecycle import Refusal
from todooit.api.model import Tellable
from todooit.ui.api.events import (
    BarNotification,
    ModeChanged,
    ModeType,
    SpawnCalendar,
)
from todooit.ui.pane_layout import PaneRow, plain_row, tree_rows
from todooit.ui.slim_cursor import slim_cursor
from todooit.ui.widgets.inputs.model_inputs import DateInput
from todooit.ui.widgets.inputs.vim_input import SLIM_CURSOR, VimDescription
from todooit.ui.widgets.renderers import (
    COLUMN_PADDING,
    DESCRIPTION_OVERFLOW,
    BaseRenderer,
)
from todooit.utils import copy_text, paste_text

from ._decorators import (
    fix_highlight,
    refresh_tree,
    require_confirmation,
    require_highlighted_node,
)
from ._render_dict import RenderDict
from .flash_jump import FlashJump

if TYPE_CHECKING:  # pragma: no cover
    from todooit.ui.api.api_components.formatters._model_formatter_base import (
        ModelFormatterBase,
    )


class ColumnRule:
    """
    A full-width hairline under the column titles. Takes whatever width it's given
    and requests none of its own, so columns size off the titles/nodes alone.
    `space_above` blank lines can push it (and what follows) down, e.g. to pin a
    block to the pane's floor.
    """

    CHARACTER = "─"

    def __init__(self, style: str, space_above: int = 0) -> None:
        self.style = style
        self.space_above = space_above

    def __rich_console__(
        self, console: Console, options: ConsoleOptions
    ) -> RenderResult:
        for _ in range(self.space_above):
            yield Segment.line()

        yield Segment(self.CHARACTER * options.max_width, console.get_style(self.style))
        yield Segment.line()

    def __rich_measure__(
        self, console: Console, options: ConsoleOptions
    ) -> Measurement:
        return Measurement(0, 0)


class GroupHeading:
    """
    A block's label plus a hairline running to the pane edge, echoing the column
    header. The blank line above it (`space_above`) separates it from the previous block.
    """

    CHARACTER = "─"

    def __init__(
        self,
        label: str,
        label_style: str,
        rule_style: str,
        space_above: bool = True,
    ) -> None:
        self.label = label
        self.label_style = label_style
        self.rule_style = rule_style
        self.space_above = space_above

    def __rich_console__(
        self, console: Console, options: ConsoleOptions
    ) -> RenderResult:
        if self.space_above:
            yield Segment.line()

        # Indent matches the rows' leftmost column padding, so the label lines up with them
        label = f"{' ' * COLUMN_PADDING}{self.label} "
        yield Segment(label, console.get_style(self.label_style))

        rule = self.CHARACTER * max(0, options.max_width - cell_len(label))
        yield Segment(rule, console.get_style(self.rule_style))
        yield Segment.line()

    def __rich_measure__(
        self, console: Console, options: ConsoleOptions
    ) -> Measurement:
        return Measurement(0, 0)


# Max chars of a description the bar will quote before truncating — enough to
# identify the row without filling the whole line
QUOTED_NAME_MAX = 40


ModelType = TypeVar("ModelType", bound=Union[Todo, Project])
RenderDictType = TypeVar("RenderDictType", bound=RenderDict)


class ModelTree(FlashJump, Generic[ModelType, RenderDictType]):
    DEFAULT_CSS = """
    ModelTree {
        height: 1fr;
        width: 1fr;
        align: center middle;

        & > Label {
            align: center middle;
        }
    }
    """

    HEADER_ID = "todooit-column-header"
    show_header: bool = False

    # Attribute a node's children hang off when expanded: "projects" or "todos"
    CHILDREN_ATTR: str = ""

    # What a row is called when the bar has to refer to one with no name
    NODE_NOUN: str = "item"

    # What I and U say when there is nowhere to move the row
    NOTHING_ABOVE: str = "Nothing above this to put it under"
    NOT_NESTED: str = "This is not under anything"

    # Rounded caps either side of the border title, matching the pane's rounded border
    TITLE_CAP_LEFT = "\ue0b6"
    TITLE_CAP_RIGHT = "\ue0b4"

    # A brief green pulse for a row whose change can't be shown by moving it
    # (e.g. a recurring todo rescheduled, not removed). ~1/3s: noticeable but
    # gone before the next key.
    FLASH_STEPS = 8
    FLASH_INTERVAL = 0.04
    FLASH_STRENGTH = 0.6

    def __init__(self, model: ModelType, render_dict: RenderDictType) -> None:
        tree = self.__class__.__name__
        super().__init__(id=f"{tree}_{model.uuid}")
        self._model = model
        self._renderers: RenderDictType = render_dict
        self._static_rows: Dict[str, Callable[[], RenderableType]] = {}

        # The rows the last refresh laid out, by option id
        self._rows: Dict[str, PaneRow] = {}

        # Rows still fading, each with the steps it has left to go
        self._flashing: Dict[str, int] = {}
        self._flash_timer: Optional[Timer] = None

        # A refresh requested while this pane was hidden, still owed. Per
        # instance: each pane tracks its own visibility
        self._needs_refresh = False

    def flash_row(self, _id: str) -> None:
        """Starts the row at full brightness and keeps the fade timer running."""

        self._flashing[_id] = self.FLASH_STEPS

        if self._flash_timer is None:
            self._flash_timer = self.set_interval(self.FLASH_INTERVAL, self._fade_rows)

        self.refresh()

    def flash_row_if_shown(self, _id: str) -> bool:
        """Flashes a row if this pane draws one for it; no-ops (rather than erroring) if not."""

        try:
            self.get_option_index(_id)
        except OptionDoesNotExist:
            return False

        self.flash_row(_id)
        return True

    def tell_outcome(self, outcome: Optional[Tellable]) -> None:
        """Says in the status bar what a lifecycle change or a move between levels did, if anything worth telling."""

        if outcome:
            self.post_message(BarNotification(outcome.summary(), "info"))

    def _fade_rows(self) -> None:
        """Advances every flashing row one step towards its background, stopping the timer once none are left."""

        for _id, step in list(self._flashing.items()):
            if step <= 1:
                self._flashing.pop(_id)
            else:
                self._flashing[_id] = step - 1

        if not self._flashing and self._flash_timer is not None:
            self._flash_timer.stop()
            self._flash_timer = None

        self.refresh()

    def _flash_background(self, step: int, under: Optional[Color]) -> Color:
        """The green a flashing row sits on, `step` steps into the fade."""

        theme = self.api.vars.theme
        base = under or Color.parse(theme.background1)
        strength = self.FLASH_STRENGTH * step / self.FLASH_STEPS

        return base.blend(Color.parse(theme.green), strength)

    def _get_option_render(self, option: Option, style: Style) -> List[Strip]:
        """Mixes the flash green into whatever background the row would otherwise have."""

        step = self._flashing.get(option.id or "")

        if step:
            style += Style(background=self._flash_background(step, style.background))

        return super()._get_option_render(option, style)

    @cache  # noqa: B019 -- cleared by hand whenever the rows change
    def get_column_width(self, attr: str) -> int:
        width = max(i._get_attr_width(attr) for i in self._renderers.values())

        if self.show_header:
            width = max(width, len(self.column_title(attr)))

        return width

    # Column headers that shouldn't just be the attribute name spelled out
    COLUMN_TITLES: Dict[str, str] = {}

    @classmethod
    def column_title(cls, attr: str) -> str:
        return cls.COLUMN_TITLES.get(attr, attr.replace("_", " ").title())

    def make_header(self) -> RenderableType:
        """Renders column names aligned with the node columns, over a rule setting them off."""

        table = Table.grid(expand=True, padding=(0, COLUMN_PADDING), pad_edge=True)
        row = []

        style = f"bold {self.api.vars.theme.primary}"

        for index, item in enumerate(self.render_layout):
            attr = item.value

            if attr == "description":
                table.add_column(attr, ratio=1, overflow=DESCRIPTION_OVERFLOW)
            else:
                width = self.get_column_width(attr)

                # Leftmost column must also hold the table's edge padding
                if index == 0:
                    width += COLUMN_PADDING

                table.add_column(attr, width=width)

            row.append(Text(self.column_title(attr), style=style))

        table.add_row(*row)
        return Group(table, ColumnRule(self.api.vars.theme.background3))

    def static_row(self, _id: str, make: Callable[[], RenderableType]) -> Option:
        """
        A row with no model behind it (column titles, a rule, a heading). Re-rendered
        from `make` on every refresh, so theme changes reach it, and disabled so the
        cursor can never land on it.
        """

        self._static_rows[_id] = make
        return Option("", id=_id, disabled=True)

    def is_static_row(self, _id: Optional[str]) -> bool:
        return _id is None or _id in self._static_rows

    def prompt_for(self, _id: str) -> RenderableType:
        make = self._static_rows.get(_id)

        if make is not None:
            return make()

        # A row added since the last layout (or outside it) draws plain
        return self.render_row(self._rows.get(_id) or plain_row(_id))

    def render_row(self, row: PaneRow) -> RenderableType:
        return self._renderers[row.uuid].make_renderable(row)

    def flash_label_column(self, index: int) -> int:
        """Past the row's edge padding and guides: over its checkbox or icon."""

        row = self._rows.get(self._options[index].id or "")
        guides = row.guides if row else ""

        return COLUMN_PADDING + cell_len(guides)

    def row_mark(self, model: ModelType) -> Text:
        """Marker drawn before a row's description; empty by default, overridden by panes that flag specific rows."""

        return Text()

    def row_note(self, model: ModelType, row: PaneRow) -> Text:
        """Note drawn after a row's description; empty by default, overridden by panes gathering rows from elsewhere."""

        return Text()

    @property
    def formatter(self) -> "ModelFormatterBase":
        raise NotImplementedError  # pragma: no cover

    @property
    def render_layout(self) -> Any:
        raise NotImplementedError  # pragma: no cover

    def column_value(self, attr: str, component: Any) -> Any:
        """The value a column is formatted from — normally just the field, unless a pane needs something coarser."""

        return component.model_value

    @property
    def editable_columns(self) -> List[str]:
        """Columns an edit may start on: everything drawn. (Subclasses may add hidden-but-editable columns.)"""

        return [item.value for item in self.render_layout]

    @property
    def current(self) -> BaseRenderer:
        _id = self.node.id
        assert _id is not None

        return self._renderers[_id]

    @property
    def current_model(self) -> ModelType:
        return self.current.model

    @property
    def is_fixed_node(self) -> bool:
        """Whether the cursor is on a fixed project rather than a stored model."""

        if self.highlighted is None or self.is_static_row(self.node.id):
            return False

        return getattr(self.current_model, "is_fixed", False)

    def update_prompt_at_index(self, index: int):
        option = self.get_option_at_index(index)
        assert option.id is not None

        self.update_prompt_by_id(option.id)

    def update_prompt_by_id(self, _id: str):
        self.replace_option_prompt(_id, self.prompt_for(_id))

    def update_current_prompt(self):
        if self.highlighted is not None:
            self.update_prompt_at_index(self.highlighted)
            self.scroll_to_highlight()

    @property
    def is_editing(self) -> bool:
        """
        Whether the highlighted row is mid-edit. Asked before the panes redraw
        from a key's change, so the highlighted row may be one that key just
        deleted: a row with no renderer isn't being edited, and none is built.
        """

        if self.highlighted is None:
            return False

        renderer = self._renderers.get(self.node.id)
        return renderer is not None and renderer.editing != ""

    @property
    def model(self) -> ModelType:
        return self._model

    @property
    def empty_message(self) -> Label:
        return self.query_one("#empty_message", expect_type=Label)

    def force_refresh(self) -> None:
        """
        Redraws now, or defers it if hidden. Panes stay mounted for the whole session
        (one per project ever visited), so redrawing a hidden pane would waste work;
        it's deferred until the pane is next shown.
        """

        if not self.display:
            self._needs_refresh = True
            return

        self._refresh_now()

    def _refresh_now(self) -> None:
        self._needs_refresh = False
        self._refresh_and_restore_highlight()

        if self.has_focus:
            self.highlight_first_node()

    def refresh_if_dirty(self) -> None:
        """Draws whatever refresh was deferred while the pane was hidden."""

        if self._needs_refresh:
            self._refresh_now()

    @on(events.Show)
    def _refresh_when_shown(self, _: events.Show) -> None:
        # Backstop: normally whoever switches to a pane refreshes it directly.
        # This catches panes shown some other way; a no-op if already drawn.
        self.refresh_if_dirty()

    @fix_highlight
    def _refresh_and_restore_highlight(self) -> None:
        self._force_refresh()
        self.get_column_width.cache_clear()

    def is_node_expanded(self, model: Any) -> bool:
        """Whether `model` is drawn open; stored on the model, so it survives a relaunch"""

        return getattr(model, "expanded", True)

    def visible_children(self, model: Any) -> List:
        """The children of a model this pane draws a row for (all of them, by default)."""

        return getattr(model, self.CHILDREN_ATTR)

    def pane_rows(self) -> List[PaneRow]:
        """The rows this pane draws, finished (see pane_layout). Overridden by panes that draw blocks."""

        return tree_rows(
            self.visible_children(self.model),
            self.visible_children,
            self.is_node_expanded,
        )

    def option_for(self, row: PaneRow) -> Option:
        """The option a laid-out row is drawn as."""

        return Option("", id=row.id)

    def _body_options(self) -> List[Option]:
        """Every row of the pane except the column titles."""

        rows = self.pane_rows()

        for row in rows:
            self._rows[row.id] = row

            # Renderers made up front, so column widths measure every row
            # rather than just those drawn so far
            if row.uuid:
                self._renderers[row.uuid]

        return [self.option_for(row) for row in rows]

    def _build_options(self) -> List[Option]:
        options = self._body_options()

        if options and self.show_header:
            options.insert(0, self.static_row(self.HEADER_ID, self.make_header))

        return options

    def _ensure_enabled_highlight(self) -> None:
        """
        Moves the cursor off a disabled/missing row after a refresh (rows shift, so a
        stale index can land on a rule, heading, or past the pane's end).
        """

        if self.highlighted is None or not self._options:
            return

        start = min(self.highlighted, len(self._options) - 1)

        for index in range(start, len(self._options)):
            if not self._options[index].disabled:
                self.highlighted = index
                return

        # Nothing below: fall back to the top, or off entirely if the pane is all rules/headings
        first = self.first_selectable_index
        self.highlighted = first if not self._options[first].disabled else None

    def _force_refresh(self) -> None:
        # The rows are rebuilt, so flash labels would point at the wrong ones
        self.cancel_flash()

        highlighted = self.highlighted
        self.clear_options()
        self._static_rows.clear()
        self._rows.clear()

        options = self._build_options()
        has_nodes = any(not self.is_static_row(option.id) for option in options)

        self.add_options(options)

        if not options:
            highlighted = None
        elif highlighted is not None:
            highlighted = min(
                max(highlighted, self.first_selectable_index),
                len(options) - 1,
            )

        self.highlighted = highlighted
        self._ensure_enabled_highlight()

        self.empty_message.display = not has_nodes
        self.refresh_options()

    def on_mount(self):
        self.force_refresh()
        self.refresh_border_title()

    def refresh_border_title(self) -> None:
        """Renders the pane title as a pill with rounded ends."""

        if not self.is_mounted or not self.BORDER_TITLE:
            return

        theme = self.api.vars.theme
        if self.has_focus:
            fill, text = theme.primary, theme.background1
        else:
            fill, text = theme.background3, theme.foreground1

        cap = f"{fill} on {theme.background1}"
        self.border_title = (
            f"[{cap}]{self.TITLE_CAP_LEFT}[/]"
            f"[{text} on {fill}]{self.BORDER_TITLE}[/]"
            f"[{cap}]{self.TITLE_CAP_RIGHT}[/]"
        )

    def watch_has_focus(self, has_focus: bool) -> None:
        super().watch_has_focus(has_focus)
        self.refresh_border_title()

    def notify_style_update(self) -> None:
        super().notify_style_update()
        self.refresh_border_title()

    def start_edit(self, property: str) -> bool:
        if property not in self.editable_columns:
            self.post_message(
                BarNotification(f"No such column: [b]{property}[/b]", "error")
            )
            return False

        res = self.current.start_edit(property)
        self.update_current_prompt()
        if res:
            self._show_mode("INSERT")
            self.app.post_message(ModeChanged("INSERT"))
            self.update_current_prompt()
        return res

    def start_vim_edit(self, property: str) -> bool:
        """
        Starts editing `property` with the note's vim keys, where the field has
        them and `api.vim.descriptions` is on; anywhere else, `start_edit`.
        """

        if not self.start_edit(property):
            return False

        component = self.current._get_component(property)

        if self.api.vim.descriptions and isinstance(component, VimDescription):
            component.start_vim(
                self.api.vim, announce=self._announce_vim_mode, report=self._report
            )
            self.update_current_prompt()

        return True

    def _announce_vim_mode(self, mode: str, pending: str) -> None:
        if mode == "INSERT":
            slim_cursor(self.app).show(self.api.vars.theme.primary)
        else:
            slim_cursor(self.app).hide()

        self._show_mode(mode)

        # Only NORMAL and INSERT get this far: the rest are switched off
        self.app.post_message(
            ModeChanged(cast(ModeType, mode), vim=True, pending=pending)
        )

    def _show_mode(self, mode: Optional[str]) -> None:
        """
        The highlighted row takes the color of the edit's mode: the panes' own
        NORMAL (`None`) keeps the plain highlight, a vim edit's NORMAL goes
        blue, INSERT green, as the note's frame does.
        """

        self.set_class(mode == "NORMAL", "-mode-normal")
        self.set_class(mode == "INSERT", "-mode-insert")

    def _report(self, message: str) -> None:
        self.post_message(BarNotification(message, "info"))

    def stop_edit(self, cancel: bool = False):
        """
        Ends the edit, keeping what was typed unless cancelled. A cancelled edit still
        leaves a brand-new, never-named item to be caught by the blank-description check below.
        """

        edited = self.current.editing

        try:
            outcome = self.current.stop_edit(cancel)
        except Refusal as refusal:
            # A rule, not a crash: the change was not made
            self.post_message(BarNotification(str(refusal), "warning"))
        except Exception as e:  # pragma: no cover
            self.post_message(BarNotification(str(e), "error", details=format_exc()))
        else:
            # What a lifecycle column's change did to other todos
            self.tell_outcome(outcome)

        slim_cursor(self.app).hide()
        self._show_mode(None)
        self.app.post_message(ModeChanged("NORMAL"))
        self.get_column_width.cache_clear()

        # A blank (or all-whitespace) description means nothing was ever given:
        # drop the item, confirming first if it has children to take with it
        if edited == "description" and not self.current_model.description.strip():
            if self._current_has_children:
                self._remove_node()
            else:
                self._discard_node()

            return

        self.update_current_prompt()

    def offer_calendar(self) -> None:
        """
        Opens the calendar when a date field's buffer contains the trigger word, checked
        after every keystroke since there's no dedicated key for it. The word is removed
        from the buffer first so an escape leaves the field as it was. Non-date fields
        just keep the word as text. Posted at the screen, like the note/move windows,
        to avoid a circular import with the screen package.
        """

        column = self.current.editing
        component = self.current._get_component(column)

        if not isinstance(component, DateInput) or not component.asks_for_calendar():
            return

        component.take_back_word()
        self.update_current_prompt()

        self.post_message(SpawnCalendar(self, column, component.calendar_day()))

    def take_picked_day(self, column: str, day: date) -> bool:
        """
        Writes a calendar-picked day into the field's buffer; the screen's follow-up
        "enter" settles it, same as a typed date. Returns whether there was still an
        edit to write into — the edit may already be gone by the time the window closes.
        """

        if not self.is_editing or self.current.editing != column:
            return False  # pragma: no cover

        component = self.current._get_component(column)

        if not isinstance(component, DateInput):
            return False  # pragma: no cover

        component.set_day(day)
        self.update_current_prompt()

        return True

    def render_line(self, y: int) -> Strip:
        strip = super().render_line(y)

        if self.is_editing and slim_cursor(self.app).shown:
            self._place_slim_cursor(strip, y)

        return strip

    def _place_slim_cursor(self, strip: Strip, y: int) -> None:
        """
        Where the field marked INSERT's cursor, as it came out in the row:
        only drawing it says how far in the column and the guides put it.
        """

        x = 0

        for segment in strip:
            style = segment.style

            if style is not None and style.meta.get(SLIM_CURSOR):
                region = self.content_region
                self.app.cursor_position = Offset(region.x + x, region.y + y)
                return

            x += segment.cell_length

    def handle_keypress(self, key: str) -> bool:
        if self.is_editing:
            component = self.current._get_component(self.current.editing)

            if isinstance(component, VimDescription) and component.engine is not None:
                # A vim edit has no key that throws it away: escape leaves
                # NORMAL by keeping the text, which the panes' `u` takes back
                if component.vim_keypress(key):
                    self.stop_edit()
            elif key in ["escape", "enter"]:
                # enter keeps the typed text; escape reverts the field
                self.stop_edit(cancel=key == "escape")
            else:
                self.current.handle_keypress(key)
                self.offer_calendar()

            self.update_current_prompt()
            return True
        else:
            if self.highlighted is not None:
                self.update_current_prompt()

        return True

    def refresh_options(self) -> None:
        # A pane owed a redraw may hold rows with no model behind them anymore;
        # let the pending rebuild handle it instead
        if self._needs_refresh:
            return

        for i in self._options:
            assert i.id is not None

            self.replace_option_prompt(i.id, self.prompt_for(i.id))

    def _get_parent(self, id: str) -> Optional[ModelType]:
        raise NotImplementedError  # pragma: no cover

    @require_highlighted_node
    def copy_description_to_clipboard(self):
        """Copies the highlighted row's description; the bar confirms since nothing visibly changes."""

        copy_text(self.app, self.current_model.description)
        self.post_message(BarNotification("Description copied to clipboard", "info"))

    @refresh_tree
    def _expand_node(self, _id: str) -> None:
        set_expanded(_id, True)

    def expand_node(self) -> None:
        if self.highlighted is not None and self.node.id:
            self._expand_node(self.node.id)

    @refresh_tree
    def _collapse_node(self, _id: str) -> None:
        set_expanded(_id, False)

    def _toggle_expand_node(self, _id: str) -> None:
        if is_expanded(_id):
            self._collapse_node(_id)
        else:
            self._expand_node(_id)

    @require_highlighted_node
    def toggle_expand(self) -> None:
        self._toggle_expand_node(self.node.id)

    def _toggle_expand_parent(self, _id: str) -> None:
        parent = self._get_parent(_id)

        if not parent or getattr(parent, "is_root", False):
            return

        parent_id = parent.uuid
        self.highlight_id(parent_id)
        self._toggle_expand_node(parent_id)

    @require_highlighted_node
    def toggle_expand_parent(self) -> None:
        self._toggle_expand_parent(self.node.id)

    def _create_child_node(self) -> ModelType:
        raise NotImplementedError  # pragma: no cover

    def add_child_node(self):
        node = self._create_child_node()
        node.description = ""
        node.save()

        self.expand_node()
        self.highlight_id(node.uuid)

        # Empty, so INSERT; escape goes on to NORMAL rather than throwing it away
        self.start_vim_edit("description")

    def _create_sibling_node(self) -> ModelType:
        return self.current_model.add_sibling()

    def highlight_id(self, _id: str):
        self.highlighted = self.get_option_index(_id)

    def highlight_id_if_shown(self, _id: str) -> bool:
        """Highlights a row if this pane draws one for it; leaves the cursor put (rather than erroring) if not."""

        try:
            self.highlight_id(_id)
        except OptionDoesNotExist:
            return False

        return True

    @refresh_tree
    def _add_sibling_node(self) -> ModelType:
        node = self._create_sibling_node()
        node.description = ""
        node.save()
        return node

    @refresh_tree
    def add_first_item(self) -> ModelType:
        return self._add_first_item()

    def _add_first_item(self) -> ModelType:
        raise NotImplementedError  # pragma: no cover

    def _new_sibling(self) -> Optional[ModelType]:
        """
        The empty node a new sibling starts out as, or None if it can't be added here
        (mid-edit, or a pane with nowhere to put one). Shared by `add_sibling` and paste.
        """

        if self.is_editing:
            return None

        if not self._options:
            return self.add_first_item()

        return self._add_sibling_node()

    def add_sibling(self):
        node = self._new_sibling()

        if node is None:
            return

        self.highlight_id(node.uuid)

        # Empty, so INSERT; escape goes on to NORMAL rather than throwing it away
        self.start_vim_edit("description")

    def _describe_node(self, node: ModelType, description: str) -> None:
        node.description = description
        node.save()

    def paste_as_sibling(self):
        """Adds a node beside the highlighted one, described by clipboard text squeezed onto one line."""

        description = " ".join(paste_text(self.app).split())

        if not description:
            self.post_message(
                BarNotification("Clipboard is empty — nothing to paste", "warning")
            )
            return

        node = self._new_sibling()

        if node is None:
            return

        self._describe_node(node, description)
        self.highlight_id(node.uuid)

    @property
    def _current_has_children(self) -> bool:
        model = self.current_model
        return bool(getattr(model, "projects", None) or getattr(model, "todos", None))

    def _delete_current_model(self) -> None:
        model = self.current_model

        self._renderers.pop(model.uuid)
        model.drop()

    def forget_rows(self, ids: Iterable[str]) -> None:
        """
        Drops renderers for models gone for good. The pane keeps a
        renderer for every model it's ever drawn (even ones since moved elsewhere),
        and column-width measurement walks all of them — a leftover renderer for a
        deleted model would look the model up and fail.
        """

        ids = set(ids)

        # Context rows are laid out under ids of their own
        for _id, row in list(self._rows.items()):
            if row.uuid in ids:
                del self._rows[_id]

        for _id in ids:
            self._renderers.pop(_id, None)

            # A pane waiting to redraw (hidden) still holds this option; drop it too,
            # since its renderer (looked up by model) is now gone
            with suppress(OptionDoesNotExist):
                self.remove_option(_id)

    def quoted_name(self) -> str:
        """The highlighted row's description, truncated for the bar; blank if it never got a name."""

        description = " ".join(self.current_model.description.split())

        if len(description) > QUOTED_NAME_MAX:
            description = description[: QUOTED_NAME_MAX - 1].rstrip() + "…"

        return escape(description)

    def quoted_subject(self) -> str:
        """The highlighted row as the bar refers to it: its name, or `NODE_NOUN` if it never got one."""

        name = self.quoted_name()
        return f"[b]{name}[/b]" if name else f"this {self.NODE_NOUN}"

    def delete_confirmation(self) -> Tuple[str, str, str]:
        """The (question, confirmed, cancelled) messages for a permanent delete, naming any children lost with it."""

        subject = self.quoted_subject()
        held = " and everything under it" if self._current_has_children else ""

        return (
            rf"Delete {subject}{held} for good? \[y/N]",
            f"Deleted {subject}{held}",
            f"Kept {subject}",
        )

    @require_confirmation
    def _remove_node(self):
        self._delete_current_model()

    @refresh_tree
    def _discard_node(self) -> None:
        """Drop the highlighted node without asking to confirm.

        Redraws itself: a node added and discarded within one edit was never
        in the database between two key presses, so the change signal has no
        row for it.
        """

        self._delete_current_model()

    def _bin_node(self) -> bool:
        """Moves the highlighted node to the Bin. Returns False if nothing moved (pane already said why)."""

        raise NotImplementedError  # pragma: no cover

    def _binned_message(self, subject: str) -> str:
        """What the bar says once the highlighted row has gone to the Bin."""

        raise NotImplementedError  # pragma: no cover

    def _restore_node(self) -> None:
        """Takes the highlighted node back out of the Bin."""

        self.post_message(
            BarNotification("Only tasks in the Bin can be restored", "warning")
        )

    @require_highlighted_node
    def remove_node(self):
        """
        Bins the highlighted item without confirming (reversible). The row disappearing
        looks identical to a real delete, so the bar spells out the difference and the way back.
        """

        subject = self.quoted_subject()
        message = self._binned_message(subject)

        if not self._bin_node():
            return

        self.post_message(BarNotification(message, "info"))

    @require_highlighted_node
    def delete_node(self):
        """
        Deletes the highlighted item outright, with everything under it — the one
        path that permanently leaves the database, so it's the one that asks first.
        `u` still reaches it until the app is quit.
        """

        self._remove_node()

    @require_highlighted_node
    def restore_node(self):
        """Puts the highlighted item back where it was thrown away from."""

        self._restore_node()

    def row_beside(self, model: Any, offset: int) -> Optional[Any]:
        """
        The row this pane draws directly above/below one, or None. Read off the pane's
        own drawn order, not the filing, since a pane can reorder or omit rows (e.g.
        completed/binned todos still filed here but drawn elsewhere).
        """

        parent = model.parent

        if parent is None:
            return None

        drawn = self.visible_children(parent)

        if model not in drawn:  # pragma: no cover
            return None

        index = drawn.index(model) + offset

        if not 0 <= index < len(drawn):
            return None

        return drawn[index]

    @require_highlighted_node
    def indent_node(self) -> None:
        """Files the highlighted row under the row drawn above it, expanding that parent so the row stays visible."""

        model = self.current_model
        parent = self.row_beside(model, -1)

        if parent is None:
            self.post_message(BarNotification(self.NOTHING_ABOVE, "warning"))
            return

        outcome = model.indent(parent)

        # Expanding refreshes the pane, placing the row where it now belongs
        self._expand_node(parent.uuid)

        # Fitted to its new parent rather than refused: say what gave way
        self.tell_outcome(outcome)

    @require_highlighted_node
    def unindent_node(self) -> None:
        """Takes the highlighted row out of the one it is filed under."""

        outcome = self.current_model.unindent()

        if outcome is None:
            self.post_message(BarNotification(self.NOT_NESTED, "warning"))
            return

        self.tell_outcome(outcome)

    def _shift(self, offset: int) -> bool:
        """Swaps the highlighted row with the one drawn beside it (by drawn position, not filing order)."""

        model = self.current_model
        neighbour = self.row_beside(model, offset)

        if neighbour is None:
            return False

        return model.swap_with(neighbour)

    def shift_up(self) -> None:
        self._shift(-1)

    def shift_down(self):
        self._shift(1)

    def compose(self) -> ComposeResult:
        with Label(id="empty_message"):
            yield Label("No items to display")
