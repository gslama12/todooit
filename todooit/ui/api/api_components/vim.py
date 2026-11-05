from todooit.vim_engine import VimKeymap

from ._base import ApiComponent


class VimManager(ApiComponent):
    """The settings of the note's vim engine: `api.vim`."""

    def __init__(self) -> None:
        self.keys = VimKeymap()
