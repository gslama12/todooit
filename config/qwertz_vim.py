"""
Standard vim navigation (h/j/k/l) on a QWERTZ keyboard

todooit's own direction keys sit one key to the right of vim's: j/k/l/ö, so
the hand rests on the home row the way it does for typing. This config moves
them back to where vim has them, and moves the two bindings that were in the
way somewhere else.

The note window, the calendar, the help screen and the attachment strip steer
with whatever keys the panes move with, so they follow along on their own.

Use it as your config:

    mkdir -p "$(dirname "$(todooit config-loc)")"
    cp config/qwertz_vim.py "$(todooit config-loc)"

or try it out once with `todooit -c config/qwertz_vim.py`.
"""

from todooit.ui.api import TodooitAPI, subscribe
from todooit.ui.api.events import Startup

# Default key -> vim key. Applied all at once, so keys can trade places.
VIM_KEYS = {
    "j": "h",  # focus the projects pane
    "ö": "l",  # focus the todos pane
    "l": "j",  # cursor down (k, cursor up, stays where it is)
    # Fold/unfold the highlighted item. `h` is taken now, so it goes to the
    # home-row key `ö` just freed up, right of `l`.
    "h": "ö",
    "L": "J",  # shift the item down (K, shift up, stays where it is)
}


@subscribe(Startup)
def vim_keys(api: TodooitAPI, _):
    api.keys.remap(VIM_KEYS)
