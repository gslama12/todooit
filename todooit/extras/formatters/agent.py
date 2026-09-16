from typing import Optional
from rich.style import Style
from rich.text import Text
from todooit.api import Todo
from todooit.ui.api import DooitAPI, extra_formatter


# An hourglass, in the same Material set the rest of the row's icons come out
# of: sand running through says the work is under way somewhere else, which is
# the whole of what the column has to report.
AGENT_ICON = "󰔟"


def agent_icon(icon: str = AGENT_ICON, color: Optional[str] = None):
    """
    The hourglass on the rows an AI has been handed, and nothing on the rest

    The flag is the whole of the column, so the icon replaces the value rather
    than leading it the way the date and recurrence icons lead theirs.
    """

    @extra_formatter
    def wrapper(value: str, model: Todo, api: DooitAPI):
        theme = api.vars.theme

        if not model.agent:
            return value

        # Appended to an empty Text rather than handed back on its own: the
        # formatter store reads a Text back as markup, and a style sitting on
        # the whole of one is not written into that -- only a span is. The
        # append is what turns the one into the other, and what keeps the
        # color on the icon by the time the row is drawn.
        return Text() + Text.from_markup(icon, style=Style(color=color or theme.primary))

    return wrapper
