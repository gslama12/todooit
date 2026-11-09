import os
import sys
from collections import defaultdict
from functools import partial
from pathlib import Path
from typing import TYPE_CHECKING, Callable, List, Optional, Type

from textual.app import ScreenStackError
from textual.css.query import NoMatches

from todooit.paths import config_file
from todooit.ui.api.event_handlers import TODOOIT_EVENT_ATTR, TODOOIT_TIMER_ATTR
from todooit.ui.api.events import TodooitEvent

from .loader import load_file

if TYPE_CHECKING:  # pragma: no cover
    from todooit.ui.api.todooit_api import TodooitAPI


if getattr(sys, "frozen", False):
    BASE_PATH = Path(sys._MEIPASS) / "todooit"  # pragma: no cover (binary pkg)
else:
    BASE_PATH = Path(__file__).parent.parent.parent

DEFAULT_CONFIG = BASE_PATH / "utils" / "default_config.py"


def is_running_under_pytest() -> bool:
    return "PYTEST_CURRENT_TEST" in os.environ


class ConfigManager:
    def __init__(self, api: "TodooitAPI", config: Optional[Path] = None) -> None:
        self.config = config or config_file()
        self.events: defaultdict[Type[TodooitEvent], List[Callable]] = defaultdict(list)
        self.api = api
        self.app = api.app

    def scan(self):
        with self.api.batch_formatter_refresh():
            load_file(self, DEFAULT_CONFIG)
            if is_running_under_pytest():
                return

            load_file(self, self.config)

    def _update_todooit_value(self, obj, *params):
        res = obj(self.api, *params)
        setattr(obj, "__todooit_value", res)

        # A timer-driven bar widget keeps ticking even when there's no bar to
        # redraw yet/anymore (before first screen push, after last pop). The
        # value is still computed and stored, so swallow the tick instead of
        # crashing the app over it.
        try:
            if bar := getattr(self.app, "bar", None):
                bar.refresh()
        except (NoMatches, ScreenStackError):
            pass

    def on_event(self, event: TodooitEvent):
        matched_events = [
            e for e in self.events if issubclass(event.__class__, e)
        ]

        # Batch so one event triggers one pane redraw regardless of how many
        # handlers answer it (startup alone registers ~40 formatters).
        with self.api.batch_formatter_refresh():
            for e in matched_events:
                for obj in self.events[e]:
                    self._update_todooit_value(obj, event)

    def _register_events(self, events: List[Type[TodooitEvent]], obj: Callable):
        for event in events:
            self.events[event].append(obj)

    def _register_timer(self, obj: Callable):
        if interval := getattr(obj, TODOOIT_TIMER_ATTR, None):
            func = partial(self._update_todooit_value, obj)
            func()
            self.api.app.set_interval(interval, func)

    def register(self, obj):
        if event := getattr(obj, TODOOIT_EVENT_ATTR, None):
            return self._register_events(event, obj)

        if getattr(obj, TODOOIT_TIMER_ATTR, None):
            return self._register_timer(obj)
