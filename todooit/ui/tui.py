from pathlib import Path
from typing import Optional
from textual import on
from textual.app import App
from textual.widgets import ContentSwitcher
from todooit.ui.api.events import ModeChanged, TodooitEvent, ModeType, Startup, QuitApp
from todooit.ui.api.events.events import ShutDown
from todooit.ui.widgets import BarSwitcher
from todooit.ui.widgets.bars import StatusBar
from todooit.ui.widgets.trees import ProjectsTree, TodosTree
from todooit.ui.screens import MainScreen
from todooit.utils import CssManager
from .api import TodooitAPI
from ..api import manager, drop_blank_models


class Todooit(App):
    CSS_PATH = CssManager().css_file
    ENABLE_COMMAND_PALETTE = False

    def __init__(
        self,
        db_path: Optional[str] = None,
        config: Optional[Path] = None,
    ):
        super().__init__(watch_css=True)
        self.todooit_mode: ModeType = "NORMAL"
        self.config = config
        manager.connect(db_path)

    def base_setup(self):
        drop_blank_models()
        self.api = TodooitAPI(self)

        # Start history after sweeping blank rows, so a row left by a mid-edit
        # quit isn't the first thing ctrl+z offers back.
        self.api.history.start()
        self.api.config_manager.scan()
        self.post_message(Startup())
        self.post_message(ModeChanged("NORMAL"))
        self.push_screen(MainScreen())

    def on_mount(self):
        self.base_setup()

    async def action_quit(self) -> None:
        drop_blank_models()
        self.post_message(ShutDown())
        return await super().action_quit()

    @property
    def project_tree(self) -> ProjectsTree:
        return self.screen.query_one(ProjectsTree)

    @property
    def todos_tree(self) -> Optional[TodosTree]:
        """The visible tasks pane, or None while the empty pane is shown.

        One pane exists per opened project; the switcher tracks which is front.
        """

        switcher = self.screen.query_one("#todo_switcher", expect_type=ContentSwitcher)
        visible = switcher.visible_content
        return visible if isinstance(visible, TodosTree) else None

    @property
    def bar(self) -> StatusBar:
        return self.bar_switcher.status_bar

    @property
    def bar_switcher(self) -> BarSwitcher:
        return self.screen.query_one(BarSwitcher)

    def get_todooit_mode(self) -> ModeType:
        return self.todooit_mode

    @on(TodooitEvent)
    def global_message(self, event: TodooitEvent):
        if isinstance(self.screen, MainScreen):
            self.api.trigger_event(event)
            self.bar.refresh()

    @on(ShutDown)
    def shutdown(self, _: ShutDown):
        self.api.css.cleanup()

    @on(ModeChanged)
    def change_status(self, event: ModeChanged):
        self.todooit_mode = event.mode
        if event.mode == "NORMAL":
            self.project_tree.refresh_options()
            todos_tree = self.todos_tree
            if todos_tree:
                todos_tree.refresh_options()

    @on(QuitApp)
    async def quit_app(self):
        await self.action_quit()


if __name__ == "__main__":  # pragma: no cover
    Todooit().run()
