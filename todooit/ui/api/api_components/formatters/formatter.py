from typing import TYPE_CHECKING

from .._base import ApiComponent
from .model_formatters import ProjectFormatter, TodoFormatter

if TYPE_CHECKING:  # pragma: no cover
    from todooit.ui.api.todooit_api import TodooitAPI


class Formatter(ApiComponent):
    def __init__(self, api: "TodooitAPI") -> None:
        self.todos = TodoFormatter(api)
        self.projects = ProjectFormatter(api)
