from todooit.vim_engine import SearchMemory, VimKeymap

from ._base import ApiComponent


class VimManager(ApiComponent):
    """The settings of the note's vim engine: `api.vim`."""

    def __init__(self) -> None:
        self.keys = VimKeymap()

        # Lasts as long as the app, for `n` to carry on in another note
        self.search = SearchMemory()
