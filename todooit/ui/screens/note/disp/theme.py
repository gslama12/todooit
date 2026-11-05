"""
The note's editor theme, painted in the todooit palette
"""

from rich.style import Style
from textual.widgets.text_area import TextAreaTheme

from todooit.api.theme import TodooitThemeBase
from todooit.utils import blend

from .markup import (
    BACKDROP,
    BULLET_SPANS,
    EMPH,
    HEADER_SPANS,
    LINK,
    MARKER,
    QUOTE,
    QUOTE_BAR,
    QUOTE_ITEM,
    RULE_SPAN,
    TARGET,
)

THEME_NAME = "todooit-note"

# How far a heading's color is faded towards the note's background, behind it
HEADER_WASH = 0.82


def build_theme(theme: TodooitThemeBase) -> TextAreaTheme:
    """
    Editor theme painted in the todooit palette rather than TextArea's default
    """

    # One color per nesting level, fading from the accent as depth increases.
    bullet_colors = (
        theme.primary,
        theme.secondary,
        blend(theme.foreground1, theme.background2, 0.35),
    )

    return TextAreaTheme(
        name=THEME_NAME,
        base_style=Style(color=theme.foreground3, bgcolor=theme.background2),
        cursor_style=Style(color=theme.background1, bgcolor=theme.primary),
        # One block of text; a highlighted cursor line would cut it in two.
        cursor_line_style=Style(),
        selection_style=Style(bgcolor=theme.background3),
        syntax_styles={
            # The only emphasis kind; orange since it's otherwise unused here.
            EMPH: Style(color=theme.orange, bold=True),
            # Stray `*` (pasted markdown / unfinished pair): faint, not
            # hidden - invisible at line-start would look like a missing indent.
            MARKER: Style(color=blend(theme.orange, theme.background2, 0.55)),
            # Quoted line drawn like markdown: green text + bar; a marker
            # inside also goes green+bold.
            QUOTE: Style(color=theme.green),
            QUOTE_BAR: Style(color=blend(theme.green, theme.background2, 0.45)),
            QUOTE_ITEM: Style(color=theme.green, bold=True),
            **{
                span: Style(color=color, bold=True)
                for span, color in zip(BULLET_SPANS, bullet_colors)
            },
            # Section break: a faint rule.
            RULE_SPAN: Style(color=blend(theme.foreground1, theme.background2, 0.7)),
            # One color per level, with a gentle wash of it behind the row.
            **{
                span: Style(
                    color=color,
                    bold=True,
                    bgcolor=blend(color, theme.background2, HEADER_WASH),
                )
                for span, color in zip(
                    HEADER_SPANS, (theme.blue, theme.purple, theme.cyan)
                )
            },
            # Same underline+italic a link wears on the todo rows.
            LINK: Style(color=theme.primary, underline=True, italic=True),
            # Text put aside, so the places to go stand out from it.
            BACKDROP: Style(color=blend(theme.foreground1, theme.background2, 0.6)),
            TARGET: Style(color=theme.background1, bgcolor=theme.red, bold=True),
        },
    )
