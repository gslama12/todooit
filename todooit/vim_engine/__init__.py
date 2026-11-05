"""
A vim editor with no screen of its own: key strings go in, and it acts on
whatever text host implements `Buffer`. Imports nothing from the UI.

- `buffer`  `Buffer`: all the engine asks of the text it edits
- `keymap`  `VimKeymap`: which keys mean what, named by `VimMotion`/`VimCommand`
- `engine`  `VimEngine`: modes, pending keys, and carrying commands out
"""

from .buffer import Buffer
from .engine import MODE_INSERT, MODE_NORMAL, VimEngine
from .keymap import VimAction, VimCommand, VimKeymap, VimMotion

__all__ = [
    "MODE_INSERT",
    "MODE_NORMAL",
    "Buffer",
    "VimAction",
    "VimCommand",
    "VimEngine",
    "VimKeymap",
    "VimMotion",
]
