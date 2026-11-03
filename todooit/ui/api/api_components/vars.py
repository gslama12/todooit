from typing import TYPE_CHECKING, Optional

from todooit.api import Project, TodoSortModeType
from todooit.api.theme import TodooitThemeBase
from todooit.ui.widgets.trees import ProjectsTree, TodosTree

from ._base import ApiComponent

if TYPE_CHECKING:  # pragma: no cover
    from todooit.ui.api.todooit_api import TodooitAPI


class VarManager(ApiComponent):
    def __init__(self, api: "TodooitAPI") -> None:
        super().__init__()
        self.api = api
        self._show_confirm = True
        self._always_expand_projects = False
        self._always_expand_todos = False
        self._todo_sort: Optional[TodoSortModeType] = "priority"
        self._projects_pane_auto_width = True
        self._projects_pane_max_width = 0.25

    @property
    def todo_sort(self) -> Optional[TodoSortModeType]:
        """
        Sort order for a stored project's todos; defaults to priority. Belongs
        to the pane, not the project, and persists across projects until
        changed. None means filed order (needed so manually dragging a row
        doesn't have it snap back under an active sort). Fixed projects order
        themselves and ignore this.
        """

        return self._todo_sort

    @todo_sort.setter
    def todo_sort(self, value: Optional[TodoSortModeType]):
        self._todo_sort = value

    @property
    def always_expand_projects(self) -> bool:
        return self._always_expand_projects

    @always_expand_projects.setter
    def always_expand_projects(self, value: bool):
        self._always_expand_projects = value

    @property
    def always_expand_todos(self) -> bool:
        return self._always_expand_todos

    @always_expand_todos.setter
    def always_expand_todos(self, value: bool):
        self._always_expand_todos = value

    @property
    def projects_pane_auto_width(self) -> bool:
        """
        Whether the projects pane is sized to its widest row (with every project
        expanded) rather than held at a fixed quarter of the screen
        """

        return self._projects_pane_auto_width

    @projects_pane_auto_width.setter
    def projects_pane_auto_width(self, value: bool):
        self._projects_pane_auto_width = value

    @property
    def projects_pane_max_width(self) -> float:
        """The most of the screen's width an auto-sized projects pane may take (0-1)"""

        return self._projects_pane_max_width

    @projects_pane_max_width.setter
    def projects_pane_max_width(self, value: float):
        self._projects_pane_max_width = value

    @property
    def show_confirm(self):
        return self._show_confirm

    @show_confirm.setter
    def show_confirm(self, value: bool):
        self._show_confirm = value

    @property
    def mode(self) -> str:
        return self.api.app.todooit_mode

    @property
    def theme(self) -> TodooitThemeBase:
        return self.api.css.theme

    # Panes are looked up via the app and handed on; config only ever sees the api.

    @property
    def projects_tree(self) -> ProjectsTree:
        return self.api.app.project_tree

    @property
    def current_project(self) -> Optional[Project]:
        tree = self.projects_tree
        if tree.highlighted is None:
            return None

        return tree.current_model

    @property
    def todos_tree(self) -> Optional[TodosTree]:
        return self.api.app.todos_tree
