from typing import Optional
from todooit.api import Todo
from rich.style import Style, StyleType
from todooit.ui.api import DooitAPI
from rich.text import Text
from todooit.ui.api import extra_formatter
import re



def description_highlight_link(color: Optional[str] = None):
    @extra_formatter
    def wrapper(value: str, _, api: DooitAPI):
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


def description_highlight_tags(color: StyleType = "", fmt=" {}"):
    @extra_formatter
    def wrapper(value: str, _: Todo, api: DooitAPI):
        """
        Highlight tags in the description.
        """

        regex = re.compile(r"@\w+")
        style = color or api.vars.theme.primary

        def highlight(match: re.Match) -> str:
            formatted_tag = fmt.format(match.group()[1:])  # strip the @ symbol
            return Text.from_markup(formatted_tag, style=style).markup

        return regex.sub(highlight, value)

    return wrapper


