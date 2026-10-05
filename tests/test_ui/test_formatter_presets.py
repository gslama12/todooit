"""
The ready-made formatters in `todooit.ui.api.formatter_presets`

Called directly with a stand-in api that carries only the theme, which is all
any of them reads.
"""

from datetime import datetime, timedelta
from types import SimpleNamespace

from rich.console import Console
from rich.text import Text

from todooit.api.theme import TokyoNight
from todooit.ui.api.api_components.formatters._decorators import (
    MUTLIPLE_FORMATTER_ATTR,
)
from todooit.ui.api.formatter_presets import (
    AGENT_ICON,
    agent_icon,
    description_highlight_link,
    due_danger_today,
    recurrence_icon,
)

CONSOLE = Console()
API = SimpleNamespace(vars=SimpleNamespace(theme=TokyoNight))


def color_at(markup: str, offset: int):
    style = Text.from_markup(markup).get_style_at_offset(CONSOLE, offset)
    return style.color.name if style.color else None


def test_icon_formatters_stack_on_the_others():
    for formatter in (agent_icon(), recurrence_icon(), description_highlight_link()):
        assert getattr(formatter, MUTLIPLE_FORMATTER_ATTR, False)

    # A plain formatter, so it can decline and let the date through
    assert not getattr(due_danger_today(), MUTLIPLE_FORMATTER_ATTR, False)


def test_agent_icon_only_on_flagged_rows():
    formatter = agent_icon()

    assert formatter("", SimpleNamespace(agent=False), API) == ""

    marked = formatter("", SimpleNamespace(agent=True), API)
    assert Text.from_markup(marked.markup).plain == AGENT_ICON
    assert color_at(marked.markup, 0) == TokyoNight.primary.lower()


def test_agent_icon_takes_its_own_icon_and_color():
    marked = agent_icon(icon="A", color="#123456")(
        "", SimpleNamespace(agent=True), API
    )

    assert marked.plain == "A"
    assert color_at(marked.markup, 0) == "#123456"


def test_recurrence_icon_leads_the_value():
    formatter = recurrence_icon(icon="R ")

    assert formatter("1w", SimpleNamespace(recurrence=None), API) == "1w"

    marked = formatter("1w", SimpleNamespace(recurrence="1w"), API)
    assert marked.plain == "R 1w"
    assert color_at(marked.markup, 0) == TokyoNight.primary.lower()


def test_description_highlight_link_marks_only_the_url():
    markup = description_highlight_link()("see https://example.com now", None, API)
    text = Text.from_markup(markup)

    assert text.plain == "see https://example.com now"
    assert not text.get_style_at_offset(CONSOLE, 0).underline
    assert text.get_style_at_offset(CONSOLE, 4).underline


def test_due_danger_today_replaces_todays_date():
    formatter = due_danger_today(fmt="<{}>")
    today = formatter(datetime.now(), None, API)

    assert Text.from_markup(today).plain == "<Today>"
    assert color_at(today, 0) == TokyoNight.red.lower()
    assert Text.from_markup(today).get_style_at_offset(CONSOLE, 0).bold


def test_due_danger_today_declines_other_days():
    formatter = due_danger_today()

    assert formatter(datetime.now() + timedelta(days=1), None, API) is None
    assert formatter(None, None, API) == ""
