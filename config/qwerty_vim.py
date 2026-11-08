"""
Standard vim navigation (h/j/k/l) on a QWERTY keyboard

todooit's own direction keys are laid out for a QWERTZ keyboard, one key to the
right of vim's: j/k/l/ö. QWERTY has no `ö`, so out of the box one of them can't
even be typed. This config moves them to where vim has them, and moves the two
bindings that were in the way somewhere else.

The calendar, the help screen and the attachment strip steer with whatever keys
the panes move with, so they follow along on their own. A note's text has keys
of its own, moved separately below.

Use it as your config:

    mkdir -p "$(dirname "$(todooit config-loc)")"
    cp config/qwerty_vim.py "$(todooit config-loc)"

or try it out once with `todooit -c config/qwerty_vim.py`.
"""

from todooit.ui.api import TodooitAPI, subscribe
from todooit.ui.api.events import Startup
from todooit.vim_engine import VimMotion

# Default key -> vim key. Applied all at once, so keys can trade places.
VIM_KEYS = {
    "j": "h",  # focus the projects pane
    "ö": "l",  # focus the todos pane
    "l": "j",  # cursor down (k, cursor up, stays where it is)
    # Fold/unfold the highlighted item. `h` is taken now, so it goes to the
    # home-row key right of `l`, which is `;` on QWERTY.
    "h": ";",
    "L": "J",  # shift the item down (K, shift up, stays where it is)
}


# The same for the cursor inside a note
VIM_NOTE_KEYS = {
    "j": "h",  # left
    "ö": "l",  # right
    "l": "j",  # down (k, up, stays where it is)
    "h": ";",  # repeat the last f F t T
    "H": ",",  # the same, the other way
    "=": "^",  # first non-blank of the line
    "_": "$",  # last character of the line
    # QWERTY has no ü or ä: the line above and below go where vim has them
    "ü": "-",
    "ä": "+",
}


@subscribe(Startup)
def vim_keys(api: TodooitAPI, _):
    api.keys.remap(VIM_KEYS)
    api.vim.keys.remap(VIM_NOTE_KEYS)
    # Free by default: a lone 0 is never a count
    api.vim.keys.set("0", VimMotion.LINE_START)

    # Flash mode's labels start on the home row too, and QWERTY's ends in `;`
    api.vars.flash_alphabet = "asdfghjkl;qwertyuiopzxcvbnm"
    api.vars.vim_flash_alphabet = "asdfghjkl;qwertyuiopzxcvbnm"

