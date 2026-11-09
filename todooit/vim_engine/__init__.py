"""
A vim editor with no screen of its own: key strings go in, and it acts on
whatever text host implements `Buffer`. Imports nothing from the UI.

- `buffer`  `Buffer`: all the engine asks of the text it edits
- `keymap`  `VimKeymap`: which keys mean what, named by `VimMotion`/`VimCommand`/`VimOperator`/`VimTextObject`
- `motions` Where a motion lands, worked out from the text
- `register` `Register`: what a yank or delete keeps, and how it stands to the clipboard;
  `YankedRange`: where a yank took it from
- `search`  `Search`: what a search looks for, and where it is in the text
- `vim_flash` `VimFlashMode`: `s`, jumping to visible text by typing it and a label
- `engine`  `VimEngine`: modes, pending keys, and carrying commands out
"""

from .buffer import Buffer
from .engine import (
    DESCRIPTION_ACTIONS,
    MODE_FLASH,
    MODE_INSERT,
    MODE_NORMAL,
    MODE_VISUAL,
    MODE_VISUAL_LINE,
    VISUAL_MODES,
    FindView,
    VimEngine,
)
from .keymap import (
    VimAction,
    VimCommand,
    VimKeymap,
    VimMotion,
    VimOperator,
    VimTextObject,
)
from .register import Register, RegisterMemory, YankedRange
from .search import Search, SearchMemory
from .vim_flash import VIM_FLASH_ALPHABET, VimFlashMatch, VimFlashView

__all__ = [
    "DESCRIPTION_ACTIONS",
    "MODE_FLASH",
    "MODE_INSERT",
    "MODE_NORMAL",
    "MODE_VISUAL",
    "MODE_VISUAL_LINE",
    "Buffer",
    "FindView",
    "Register",
    "RegisterMemory",
    "Search",
    "VISUAL_MODES",
    "VIM_FLASH_ALPHABET",
    "SearchMemory",
    "VimAction",
    "VimCommand",
    "VimEngine",
    "VimFlashMatch",
    "VimFlashView",
    "VimKeymap",
    "VimMotion",
    "VimOperator",
    "VimTextObject",
    "YankedRange",
]
