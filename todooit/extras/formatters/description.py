from typing import Optional
from rich.style import Style
from todooit.ui.api import TodooitAPI
from rich.text import Text
from todooit.ui.api import extra_formatter
import re



def description_highlight_link(color: Optional[str] = None):
    @extra_formatter
    def wrapper(value: str, _, api: TodooitAPI):
        """
        Highlight URLs in the description.
        """

        url_pattern = re.compile(
            r"http[s]?://"
            r"(?:[a-zA-Z]|[0-9]|[$-_@.&+]|[!*\\(\\),]|"
            r"(?:%[0-9a-fA-F][0-9a-fA-F]))+",
            re.IGNORECASE,
        )

        text = Text.from_markup(value)
        text.highlight_regex(
            url_pattern,
            style=Style(
                color=color or api.vars.theme.primary,
                underline=True,
                italic=True,
            ),
        )

        return text.markup

    return wrapper
