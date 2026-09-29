from pathlib import Path
from typing import Optional
from textual import on
from textual.app import App
from todooit.ui.api.events import ModeChanged, TodooitEvent, ModeType, Startup, QuitApp
from todooit.ui.api.events.events import ShutDown
from todooit.ui.widgets import BarSwitcher
from todooit.ui.widgets.bars import StatusBar
from todooit.ui.widgets.trees import ProjectsTree
from todooit.ui.screens import MainScreen
from todooit.ui.widgets.trees.model_tree import ModelTree
from todooit.utils import CssManager, open_url
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

        # After the blank rows have been swept up, so that a row left behind
        # by a session that quit mid-edit is not the first thing ctrl+z offers
        # to bring back
        self.api.history.start()
        self.api.plugin_manager.scan()
        self.post_message(Startup())
        self.post_message(ModeChanged("NORMAL"))
        self.push_screen(MainScreen())

    def setup_poller(self):
        self.set_interval(1, self.poll_todooit_db)

    def on_mount(self):
        self.base_setup()
        self.setup_poller()

    async def action_quit(self) -> None:
        drop_blank_models()
        self.post_message(ShutDown())
        return await super().action_quit()

    @property
    def project_tree(self) -> ProjectsTree:
        return self.screen.query_one(ProjectsTree)

    @property
    def bar(self) -> StatusBar:
        return self.screen.query_one(BarSwitcher).status_bar

    @property
    def bar_switcher(self) -> BarSwitcher:
        return self.screen.query_one(BarSwitcher)

    def get_todooit_mode(self) -> ModeType:
        return self.todooit_mode

    def poll_todooit_db(self):  # pragma: no cover
        def refresh_all_trees():
            trees = self.screen.query(ModelTree)
            for tree in trees:
                tree.force_refresh()

        if manager.has_changed():
            # Rows that arrived from somewhere else are not a change made here
            # to be taken back, so they become what the next key is measured
            # against instead of being folded into whatever it does
            self.api.history.resync()
            refresh_all_trees()

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
            todos_tree = self.api.vars.todos_tree
            if todos_tree:
                todos_tree.refresh_options()

    @on(QuitApp)
    async def quit_app(self):
        await self.action_quit()

    def action_open_url(self, url: str) -> None:  # pragma: no cover
        # todooit's own opener rather than textual's: `App.open_url` goes
        # through `webbrowser`, which finds nothing at all under WSL - the
        # same reason the "o" key does not go through it either
        open_url(url)


if __name__ == "__main__":  # pragma: no cover
    Todooit().run()
