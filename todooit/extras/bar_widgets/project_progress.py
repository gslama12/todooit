from typing import Union
from todooit.ui.api import DooitAPI, subscribe
from todooit.ui.api.events import ProjectSelected, TodoEvent
from todooit.api import Project
from .text_poller import Custom


def get_completed(project: Project):
    """
    Get the percentage of completed todos in the project
    """

    todos = project.todos

    if not todos:
        return 0

    complete_count = sum(t.is_completed for t in todos)
    total_count = len(todos)

    return int(100 * complete_count / total_count)


@subscribe(ProjectSelected, TodoEvent)
def get_project_completion(
    api: DooitAPI,
    event: Union[ProjectSelected, TodoEvent],
) -> str:
    if isinstance(event, ProjectSelected):
        project = event.project
    elif isinstance(event, TodoEvent):
        project = api.app.project_tree.current_model

    return str(get_completed(project))


class ProjectProgress(Custom):
    def __init__(self, api: DooitAPI, fmt="{}", fg: str = "", bg: str = "") -> None:
        super().__init__(
            api=api,
            function=get_project_completion,
            width=None,
            fmt=fmt,
            fg=fg,
            bg=bg,
        )
