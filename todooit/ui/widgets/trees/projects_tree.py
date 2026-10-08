from typing import TYPE_CHECKING, List, Optional
from textual import on
from textual.widgets.option_list import Option

from todooit.api import Project, fixed_projects, move_project_to_bin
from todooit.ui.api.events import ProjectSelected
from .model_tree import ColumnRule, ModelTree
from ._decorators import reject_fixed_node, require_highlighted_node
from ._render_dict import ProjectRenderDict


if TYPE_CHECKING:  # pragma: no cover
    from todooit.ui.api.api_components.formatters.model_formatters import (
        ProjectFormatter,
    )


class ProjectsTree(ModelTree[Project, ProjectRenderDict]):
    BORDER_TITLE = "PROJECTS"
    NODE_NOUN = "project"
    show_header = True
    CHILDREN_ATTR = "projects"

    # What I and U say when there is nowhere to move the project
    NOTHING_ABOVE = "No project above this to put it under"
    NOT_NESTED = "This project is not under another one"

    # A project's description is just what it's called
    COLUMN_TITLES = {"description": "Name"}

    # Rules separating fixed projects from stored ones, drawn with the same
    # hairline as the column header so they read as pane furniture, not a project
    FIXED_RULE_ID = "todooit-fixed-projects-rule"
    BOTTOM_RULE_ID = "todooit-bottom-projects-rule"

    FIXED_MESSAGE = "[b]{}[/b] is a fixed project and can't be changed"

    def __init__(self, model: Project) -> None:
        render_dict = ProjectRenderDict(self)
        super().__init__(model, render_dict)
        self._bottom_gap = 0

    def _body_options(self) -> List[Option]:
        """
        Fixed projects, then stored projects, then bottom-pinned fixed projects.
        A rule divides each block, but only when there's something on both sides.
        The bottom block is pushed to the pane's floor via blank lines above its rule.
        """

        top: List[Option] = []
        bottom: List[Option] = []

        for project in fixed_projects():
            option = Option("", id=self._renderers[project.uuid].id)
            (bottom if project.pinned_bottom else top).append(option)

        stored = super()._body_options()
        options = list(top)

        if top and stored:
            options.append(self.static_row(self.FIXED_RULE_ID, self._make_fixed_rule))

        options += stored

        if bottom:
            if top or stored:
                options.append(
                    self.static_row(self.BOTTOM_RULE_ID, self._make_bottom_rule)
                )

            options += bottom

        return options

    def _make_fixed_rule(self) -> ColumnRule:
        return ColumnRule(self.api.vars.theme.background3)

    def _make_bottom_rule(self) -> ColumnRule:
        return ColumnRule(self.api.vars.theme.background3, space_above=self._bottom_gap)

    def _sync_bottom_gap(self) -> None:
        """Sizes the blank space holding the pinned block against the pane floor (0 once rows fill it)."""

        if self.BOTTOM_RULE_ID not in self._static_rows:
            return

        height = self.scrollable_content_region.height
        if height <= 0:
            return

        heights = self._heights
        if len(heights) != len(self._options):
            return

        # Subtract the previous gap so only real rows (incl. the rule's hairline) count as filled
        filled = sum(heights.values()) - self._bottom_gap
        gap = max(0, height - filled)

        if gap != self._bottom_gap:
            self._bottom_gap = gap
            self.refresh_options()

    def _force_refresh(self) -> None:
        super()._force_refresh()
        self._sync_bottom_gap()

    def _remeasure_bottom_gap(self) -> None:
        """Re-measures a frame later, since layout from a resizing event settles after this call runs."""

        self.call_after_refresh(self._sync_bottom_gap)

    def notify_style_update(self) -> None:
        # On first launch the app's CSS can land after the pane's first size,
        # while it's still using OptionList's default padding (2 rows more
        # than the real border), overstating the floor by 2 lines. That's
        # enough to push the pinned block off-screen. No resize event follows
        # (the border keeps the same outer shape), so this is the only signal
        # we get that the floor changed.
        super().notify_style_update()
        self._remeasure_bottom_gap()

    def on_resize(self, _) -> None:
        self._sync_bottom_gap()

    def _stored_indices(self) -> List[int]:
        """
        Pane rows for database-held projects, excluding the fixed blocks (top/bottom
        of pane already jump there via their own keys).
        """

        indices: List[int] = []

        for index, option in enumerate(self._options):
            if option.disabled or self.is_static_row(option.id):
                continue

            assert option.id is not None

            if getattr(self._renderers[option.id].model, "is_fixed", False):
                continue

            indices.append(index)

        return indices

    def action_first(self) -> None:
        indices = self._stored_indices()

        if not indices:
            return super().action_first()

        self.highlighted = indices[0]

    def action_last(self) -> None:
        indices = self._stored_indices()

        if not indices:
            return super().action_last()

        self.highlighted = indices[-1]

    @require_highlighted_node
    @reject_fixed_node(FIXED_MESSAGE)
    def set_color(self, color: int) -> None:
        """
        Sets the highlighted project's (sub)tree to a palette slot, or clears it if
        already that color. Colors the whole subtree, so the pane redraws in full.
        """

        project = self.current_model
        assert isinstance(project, Project)

        project.set_color(None if project.color == color else color)
        self.refresh_options()
        self.scroll_to_highlight()

    def _get_parent(self, id: str) -> Optional[Project]:
        return Project.from_id(id).parent_project

    def is_node_expaned(self, _id: str) -> bool:
        return super().is_node_expaned(_id) or self.api.vars.always_expand_projects

    @property
    def formatter(self) -> "ProjectFormatter":
        return self.api.formatter.projects

    @property
    def render_layout(self):
        return self.api.layouts.project_layout

    def add_project(self) -> str:
        project = self.model.add_project()
        self.add_option(Option(self.prompt_for(project.uuid), id=project.uuid))
        return project.uuid

    def _create_child_node(self) -> Project:
        return self.current_model.add_project()

    def _add_first_item(self) -> Project:
        return self.model.add_project()

    def _bin_node(self) -> bool:
        """
        Drops the highlighted project, but not its tasks: they move to the Bin
        carrying their origin path, so restoring one rebuilds the project.
        """

        project = self.current_model

        self._renderers.pop(project.uuid, None)
        self.expanded_nodes.pop(project.uuid, None)

        move_project_to_bin(project)
        return True

    def _discard_node(self) -> None:
        """
        Also drops the discarded project's tasks pane, which the change signal
        never names as gone (the row didn't outlive the edit). Left mounted, it
        would be picked up again by the next new project: SQLite hands the
        discarded row's id straight back out, and panes are found by that id.
        """

        from todooit.ui.screens.index import MainScreen

        uuid = self.current_model.uuid
        super()._discard_node()

        if isinstance(self.screen, MainScreen):
            self.screen.drop_project_pane(uuid)

    def _binned_message(self, subject: str) -> str:
        """Points at the Bin (its tasks, not the dropped project itself) when there were tasks to move."""

        if self._current_has_children:
            return f"Dropped {subject} — its tasks are in the Bin"

        return f"Dropped {subject}"

    # ---------------------------------------------------------------
    # Nothing about a fixed project is stored, so every edit that would
    # write one back to the database is turned away with a word about why
    # ---------------------------------------------------------------

    @reject_fixed_node(FIXED_MESSAGE)
    def start_edit(self, property: str) -> bool:
        return super().start_edit(property)

    @reject_fixed_node(FIXED_MESSAGE)
    def add_child_node(self):
        return super().add_child_node()

    @reject_fixed_node(FIXED_MESSAGE)
    def remove_node(self):
        return super().remove_node()

    @reject_fixed_node(FIXED_MESSAGE)
    def delete_node(self):
        return super().delete_node()

    @reject_fixed_node(FIXED_MESSAGE)
    def shift_up(self) -> None:
        return super().shift_up()

    @reject_fixed_node(FIXED_MESSAGE)
    def shift_down(self):
        return super().shift_down()

    @reject_fixed_node(FIXED_MESSAGE)
    def indent_node(self) -> None:
        return super().indent_node()

    @reject_fixed_node(FIXED_MESSAGE)
    def unindent_node(self) -> None:
        return super().unindent_node()

    def _new_sibling(self) -> Optional[Project]:
        """A fixed project has no siblings, so a new sibling there goes to the top level instead."""

        if self.is_fixed_node:
            if self.is_editing:
                return None

            return self.add_first_item()

        return super()._new_sibling()

    @on(ModelTree.OptionHighlighted)
    def project_highlighted(self, event: ModelTree.OptionHighlighted):
        assert event.option_id

        event.stop()

        if self.is_static_row(event.option_id):
            return

        self.post_message(ProjectSelected(self._renderers[event.option_id].model))
