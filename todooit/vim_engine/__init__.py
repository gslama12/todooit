"""
A vim editor with no screen of its own: key strings go in, and it acts on
whatever text host implements `Buffer`. Imports nothing from the UI.

- `buffer`  `Buffer`: all the engine asks of the text it edits
- `keymap`  `VimKeymap`: which keys mean what, named by `VimMotion`/`VimCommand`/`VimOperator`
- `motions` Where a motion lands, worked out from the text
- `engine`  `VimEngine`: modes, pending keys, and carrying commands out
"""

from .buffer import Buffer
from .engine import MODE_INSERT, MODE_NORMAL, FindView, Register, VimEngine
from .keymap import VimAction, VimCommand, VimKeymap, VimMotion, VimOperator

__all__ = [
    "MODE_INSERT",
    "MODE_NORMAL",
    "Buffer",
    "FindView",
    "Register",
    "VimAction",
    "VimCommand",
    "VimEngine",
    "VimKeymap",
    "VimMotion",
    "VimOperator",
]
