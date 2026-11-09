from todooit.vim_engine import RegisterMemory, SearchMemory, VimKeymap

from ._base import ApiComponent


class VimManager(ApiComponent):
    """The settings of the vim engine, in notes and descriptions: `api.vim`."""

    def __init__(self) -> None:
        self.keys = VimKeymap()

        # Lasts as long as the app, for `n` to carry on in another note
        self.search = SearchMemory()

        # Likewise, for a yank in one note to paste in another, or in a
        # description
        self.register = RegisterMemory()

        # Whether `edit_description_vim` edits a todo's or a project's
        # description with these keys too. Off, it's the same as `i`.
        self.descriptions: bool = True
