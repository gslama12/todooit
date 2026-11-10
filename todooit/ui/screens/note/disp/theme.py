"""
The note's editor theme, painted in the todooit palette
"""

from rich.style import Style
from textual.widgets.text_area import TextAreaTheme

from todooit.api.theme import TodooitThemeBase
from todooit.utils import blend
from todooit.vim_engine import (
    MODE_FLASH,
    MODE_INSERT,
    MODE_NORMAL,
    MODE_VISUAL,
    MODE_VISUAL_LINE,
)

from .markup import (
    BACKDROP,
    BOLD,
    BOLD_ITALIC,
    BULLET_SPANS,
    GUTTER,
    GUTTER_CURSOR,
    HEADER_SPANS,
    HIGHLIGHT,
    ITALIC,
    LINK,
    MARKED,
    MARKED_FIRST,
    MARKER,
    QUOTE,
    QUOTE_BAR,
    QUOTE_ITEM,
    RULE_SPAN,
    SEARCH_MATCH,
    SELECTED,
    TARGET,
    YANKED,
)

THEME_NAME = "todooit-note"

# How far a heading's color is faded towards the note's background, behind it
HEADER_WASH = 0.82

# How far the gutter's line numbers are faded towards it
GUTTER_FADE = 0.5

# Each mode's color, as lualine paints LazyVim's: the mode chip, the frame's
# border and the mode's heading in the help pane. Names of theme colors.
MODE_COLORS = {
    MODE_NORMAL: "blue",
    MODE_INSERT: "green",
    MODE_VISUAL: "magenta",
    MODE_VISUAL_LINE: "magenta",
    MODE_FLASH: "orange",
}


# How far the text a character jump looks across is faded towards the
# background: put aside, but still easy to read
BACKDROP_FADE = 0.35


def backdrop_style(theme: TodooitThemeBase) -> Style:
    """Text a character jump looks across, put aside; a description's too."""

    return Style(color=blend(theme.foreground1, theme.background2, BACKDROP_FADE))


def selection_style(theme: TodooitThemeBase) -> Style:
    """A selection, as a field being edited draws one: the inverted accent."""

    return Style(color=theme.background1, bgcolor=theme.secondary)


def target_style(theme: TodooitThemeBase) -> Style:
    """Where a character jump can land."""

    return Style(color=theme.background1, bgcolor=theme.red, bold=True)


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
        selection_style=selection_style(theme),
        syntax_styles={
            # Real weight and slant, in whatever color the text around has
            ITALIC: Style(italic=True),
            BOLD: Style(bold=True),
            BOLD_ITALIC: Style(bold=True, italic=True),
            # `==x==`: picked out in orange, since it's otherwise unused here
            HIGHLIGHT: Style(color=theme.orange, bold=True),
            # The marks of a pair on the cursor line (`*`, `_`, `=`): faint, not hidden -
            # invisible at line-start would look like a missing indent.
            MARKER: Style(color=blend(theme.foreground3, theme.background2, 0.55)),
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
            BACKDROP: backdrop_style(theme),
            TARGET: target_style(theme),
            SEARCH_MATCH: Style(color=theme.background1, bgcolor=theme.yellow),
            MARKED: Style(color=theme.background1, bgcolor=theme.blue),
            MARKED_FIRST: Style(color=theme.background1, bgcolor=theme.cyan),
            # V-LINE's whole lines, as the selection itself looks.
            SELECTED: selection_style(theme),
            # Line numbers: the cursor's own stands out, as in LazyVim.
            GUTTER: Style(
                color=blend(theme.foreground1, theme.background2, GUTTER_FADE)
            ),
            GUTTER_CURSOR: Style(color=theme.orange, bold=True),
            # What was just yanked, for a moment, as `vim.hl.on_yank()` does.
            YANKED: Style(color=theme.background1, bgcolor=theme.orange),
        },
    )
