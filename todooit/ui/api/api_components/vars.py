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
        self._row_shading = False
        self._todo_sort: Optional[TodoSortModeType] = "priority"

    @property
    def todo_sort(self) -> Optional[TodoSortModeType]:
        """
        The order the todos of a stored project are read in

        Priority to start with: a project is a pile of work, and what is asked
        of it first is what to do next. An order picked instead of it belongs
        to the pane rather than to the project that was open at the time, and
        holds until it is switched again.

        None means no order is being worked out over the rows at all and they
        are read in the order they are filed in — which is where moving a row
        by hand puts the pane, since a row dragged up a sorted pane would
        otherwise drop straight back where the sort wants it.

        Fixed projects order their own rows and are left alone by this.
        """

        return self._todo_sort

    @todo_sort.setter
    def todo_sort(self, value: Optional[TodoSortModeType]):
        self._todo_sort = value

    @property
    def row_shading(self) -> bool:
        """Whether every other todo row is tinted to help the eye track it"""

        return self._row_shading

    @row_shading.setter
    def row_shading(self, value: bool):
        self._row_shading = value

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

    # The panes are looked up by the app; these hand them on to the config,
    # which is given the api and never the app itself

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
