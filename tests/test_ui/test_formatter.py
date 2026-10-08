from typing import Optional

from rich.style import Style
from rich.text import Text

from tests.test_ui.ui_base import run_pilot
from todooit.api.project import Project
from todooit.ui.api import extra_formatter
from todooit.ui.api.api_components.formatters import FormatterStore
from todooit.ui.api.todooit_api import TodooitAPI
from todooit.ui.tui import Todooit


def set_italic(value: str, _: Project, api: TodooitAPI) -> Optional[str]:
    text_value = Text(value)
    text_value.highlight_words(
        ["test"],
        Style(
            italic=True,
            color=api.vars.theme.red,
        ),
    )
    return text_value.markup


@extra_formatter
def add_icon(value: str, _: Project) -> Optional[str]:
    if "123" in value:
        return f"(icon) {value}"


def add_icon_skip_multiple(value: str, _: Project) -> Optional[str]:
    if "123" in value:
        return f"(icon) {value}"


def setup(api: TodooitAPI):
    store = FormatterStore(lambda: None, api)
    p1 = Project(description="this is a test description")
    p2 = Project(description="another description 123")
    return store, p1, p2


def italic_test(api: TodooitAPI) -> str:
    """The word "test" as `set_italic` marks it, in the theme's own red

    Rich normalizes hex colors to lowercase on the way through a Style, so
    the expectation has to be lowercased too.
    """

    red = api.vars.theme.red.lower()
    return f"[italic {red}]test[/italic {red}]"


async def test_no_formatting():
    async with run_pilot() as pilot:
        app = pilot.app
        assert isinstance(app, Todooit)
        store, p1, p2 = setup(app.api)

        formatted = store.format_value(p1.description, p1)
        assert formatted.markup == "this is a test description"

        formatted = store.format_value(p2.description, p2)
        assert formatted.markup == "another description 123"


async def test_basic_formatting():
    async with run_pilot() as pilot:
        app = pilot.app
        assert isinstance(app, Todooit)
        store, p1, p2 = setup(app.api)

        store.add(set_italic)
        formatted = store.format_value(p1.description, p1)
        assert formatted.markup == f"this is a {italic_test(app.api)} description"

        formatted = store.format_value(p2.description, p2)
        assert formatted.markup == "another description 123"


async def test_multiple_formatting():
    async with run_pilot() as pilot:
        app = pilot.app
        assert isinstance(app, Todooit)
        store, p1, p2 = setup(app.api)

        store.add(set_italic)
        store.add(add_icon)
        formatted = store.format_value(p1.description, p1)
        assert formatted.markup == f"this is a {italic_test(app.api)} description"

        formatted = store.format_value(p2.description, p2)
        assert formatted.markup == "(icon) another description 123"


async def test_multiple_formatting_skip():
    async with run_pilot() as pilot:
        app = pilot.app
        assert isinstance(app, Todooit)
        store, p1, p2 = setup(app.api)
        p2.description = "another description 123 test"

        store.add(set_italic)
        store.add(add_icon_skip_multiple)
        formatted = store.format_value(p1.description, p1)
        assert formatted.markup == f"this is a {italic_test(app.api)} description"

        formatted = store.format_value(p2.description, p2)
        assert formatted.markup == "(icon) another description 123 test"


async def test_multiple_formatting_toggle():
    async with run_pilot() as pilot:
        app = pilot.app
        assert isinstance(app, Todooit)
        store, p1, _ = setup(app.api)

        p1.description += " 123"

        store.add(set_italic, id="italic")
        store.add(add_icon, id="icon")
        formatted = store.format_value(p1.description, p1)
        assert (
            formatted.markup
            == f"(icon) this is a {italic_test(app.api)} description 123"
        )

        assert store.disable("italic")
        formatted = store.format_value(p1.description, p1)
        assert formatted.markup == "(icon) this is a test description 123"

        assert store.disable("icon")
        formatted = store.format_value(p1.description, p1)
        assert formatted.markup == "this is a test description 123"

        assert store.enable("italic")
        formatted = store.format_value(p1.description, p1)
        assert formatted.markup == f"this is a {italic_test(app.api)} description 123"

        assert not store.enable("random_gibberish_id")
        assert not store.disable("random_gibberish_id")

        store.remove("italic")
        formatted = store.format_value(p1.description, p1)
        assert formatted.markup == "this is a test description 123"


async def test_a_batch_redraws_once_however_many_formatters_it_holds():
    """
    Registering a run of formatters is one change to how the panes are drawn

    The config lays down forty-odd of them at startup, and every one used to
    rebuild every pane on its own -- forty-one full redraws to show the one
    the last of them produced.
    """

    async with run_pilot() as pilot:
        app = pilot.app
        assert isinstance(app, Todooit)

        fired = []
        store = FormatterStore(lambda: fired.append(1), app.api)

        with app.api.batch_formatter_refresh():
            for _ in range(10):
                store.add(add_icon_skip_multiple)

            # Nothing is drawn while the batch is open
            assert fired == []

        assert fired == [1]


async def test_a_formatter_added_outside_a_batch_redraws_at_once():
    """Batching is for a run of them; one on its own still shows immediately"""

    async with run_pilot() as pilot:
        app = pilot.app
        assert isinstance(app, Todooit)

        fired = []
        store = FormatterStore(lambda: fired.append(1), app.api)

        store.add(add_icon_skip_multiple)
        assert fired == [1]


async def test_a_batch_keeps_every_distinct_trigger():
    """
    Two panes are two redraws

    The triggers dedupe so that one pane is not drawn ten times, not so that
    a second pane is dropped.
    """

    async with run_pilot() as pilot:
        app = pilot.app
        assert isinstance(app, Todooit)

        todos, projects = [], []
        todo_store = FormatterStore(lambda: todos.append(1), app.api)
        project_store = FormatterStore(lambda: projects.append(1), app.api)

        with app.api.batch_formatter_refresh():
            todo_store.add(add_icon_skip_multiple)
            project_store.add(add_icon_skip_multiple)
            todo_store.add(set_italic)

        assert todos == [1]
        assert projects == [1]


async def test_a_raising_handler_still_closes_the_batch():
    """
    A batch left open would swallow every redraw for the rest of the session
    """

    async with run_pilot() as pilot:
        app = pilot.app
        assert isinstance(app, Todooit)

        fired = []
        store = FormatterStore(lambda: fired.append(1), app.api)

        try:
            with app.api.batch_formatter_refresh():
                store.add(add_icon_skip_multiple)
                raise RuntimeError("a config that blew up")
        except RuntimeError:
            pass

        # What it had collected was still drawn, and the batch is closed
        assert fired == [1]
        assert app.api._formatter_batch is None

        store.add(set_italic)
        assert fired == [1, 1]
