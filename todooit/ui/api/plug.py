import os
import sys
from functools import partial
from collections import defaultdict
from pathlib import Path
from typing import TYPE_CHECKING, Callable, List, Optional, Type
from textual.app import ScreenStackError
from textual.css.query import NoMatches

from todooit.ui.api.event_handlers import TODOOIT_EVENT_ATTR, TODOOIT_TIMER_ATTR
from todooit.ui.api.events import TodooitEvent
from todooit.paths import config_file
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


class PluginManager:
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

        # A bar widget on a timer goes on ticking whatever else is happening,
        # and at both ends of the app's life there is no bar for it to redraw:
        # on the way up no screen has been pushed yet, and on the way down the
        # last one has already been popped. Neither is worth reporting -- the
        # value has been worked out and kept either way, and whatever draws it
        # next reads it from there -- so the tick is let go quietly rather than
        # being allowed to take the app down with it.
        try:
            if bar := getattr(self.app, "bar", None):
                bar.refresh()
        except (NoMatches, ScreenStackError):
            pass

    def on_event(self, event: TodooitEvent):
        matched_events = [
            e for e in self.events.keys() if issubclass(event.__class__, e)
        ]

        # One event is one change as far as the panes are concerned, however
        # many handlers answer it. The formatters the startup handlers lay
        # down are the case that matters -- there are forty-odd of them, and
        # without this each one rebuilds every pane on its own
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
