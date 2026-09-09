from typing import Union
from dooit.ui.api import DooitAPI, subscribe
from dooit.ui.api.events import Startup, ProjectSelected
from .text_poller import Custom


def get_project_name_wrapper(no_project_text: str):
    @subscribe(ProjectSelected, Startup)
    def get_project_name(
        _: DooitAPI, event: Union[ProjectSelected, Startup]
    ) -> str:
        if isinstance(event, Startup):
            return no_project_text

        text = event.project.description
        parent = event.project.parent_project

        if parent and not parent.is_root:
            text = f"{parent.description}/{text}"

        return text

    return get_project_name


class CurrentProject(Custom):
    def __init__(
        self,
        api: DooitAPI,
        no_project_text="No Project Selected",
        fmt=" {} ",
        fg: str = "",
        bg: str = "",
    ) -> None:
        super().__init__(
            api=api,
            function=get_project_name_wrapper(no_project_text),
            width=None,
            fmt=fmt,
        )

        self.fg = fg
        self.bg = bg
