"""
The ready-made status bar widgets and the StatusBarWidget they are built on

The widgets' functions are called directly, the way the config manager calls
them, so none of this waits on a timer or an event going round the app.
"""

from datetime import datetime
from types import SimpleNamespace

from rich.style import Style
from rich.console import Console
from rich.text import Text

from todooit.ui.api.bar_widgets import clock, current_project, spacer, text
from todooit.ui.api.events import Startup
from todooit.ui.widgets.bars import StatusBarWidget
from tests.test_ui.ui_base import boot, run_pilot


CONSOLE = Console()


def settled(widget: StatusBarWidget, *params) -> StatusBarWidget:
    """Stores the widget's value the way the config manager does"""

    setattr(widget.func, "__todooit_value", widget.func(*params))
    return widget


def test_render_paints_fg_and_bg_under_the_value():
    widget = settled(StatusBarWidget(lambda *_: "hi", fg="#111111", bg="#222222"))
    rendered = widget.render()

    assert rendered.plain == "hi"
    assert rendered.style == Style(color="#111111", bgcolor="#222222")


def test_markup_in_the_value_wins_over_the_segment_colors():
    widget = settled(
        StatusBarWidget(lambda *_: "[#333333]hi[/]", fg="#111111", bg="#222222")
    )
    rendered = widget.render()

    assert rendered.get_style_at_offset(CONSOLE, 0).color.name == "#333333"
    assert rendered.get_style_at_offset(CONSOLE, 0).bgcolor.name == "#222222"


def test_fmt_wraps_the_value():
    widget = settled(StatusBarWidget(lambda *_: "x", fmt="[bold] <{}> [/]"))
    rendered = widget.render()

    assert rendered.plain == " <x> "
    assert rendered.get_style_at_offset(CONSOLE, 1).bold


def test_a_text_value_keeps_its_markup():
    widget = settled(StatusBarWidget(lambda *_: Text("hi", style="bold")))

    assert widget.render().get_style_at_offset(CONSOLE, 0).bold


def test_an_unset_widget_renders_empty():
    assert StatusBarWidget(lambda *_: "never stored").render().plain == ""


def test_text_is_fixed_from_startup():
    widget = settled(text("cap", fg="#111111"), None, Startup())

    assert widget.render().plain == "cap"
    assert widget.width is None


def test_spacer_is_blank_at_its_width():
    widget = spacer(width=4, bg="#222222")

    assert widget.render().plain == ""
    assert widget.width == 4
    assert spacer().width == 0


def test_clock_reads_the_time_in_its_format():
    widget = settled(clock(format="%Y", fmt="<{}>"))

    assert widget.render().plain == f"<{datetime.now().year}>"


def test_current_project_before_anything_is_selected():
    widget = settled(current_project(no_project_text="none"), None, Startup())

    assert widget.render().plain == " none "


def test_current_project_names_the_parent_of_a_subproject():
    root = SimpleNamespace(is_root=True)
    parent = SimpleNamespace(description="work", parent_project=root, is_root=False)
    child = SimpleNamespace(description="taxes", parent_project=parent)

    widget = current_project(fmt="{}")

    settled(widget, None, SimpleNamespace(project=parent))
    assert widget.render().plain == "work"

    settled(widget, None, SimpleNamespace(project=child))
    assert widget.render().plain == "work/taxes"


async def test_the_config_bar_is_built_from_these_widgets():
    async with run_pilot() as pilot:
        app = await boot(pilot)
        rendered = [widget.render().plain for widget in app.bar.bar_widgets]

        assert any("NORMAL" in plain for plain in rendered)
        # The project the app opens on, named by `current_project`
        assert any("Today" in plain for plain in rendered)
