from typing import TYPE_CHECKING

from .formatter_store import FormatterStore

if TYPE_CHECKING:  # pragma: no cover
    from todooit.ui.api.todooit_api import TodooitAPI


class ModelFormatterBase:
    def __init__(self, api: "TodooitAPI") -> None:
        self.api = api
        self.setup_formatters()

    def get_formatter_store(self) -> FormatterStore:
        return FormatterStore(self.trigger, self.api)

    def setup_formatters(self) -> None:  # pragma: no cover
        pass

    def trigger(self) -> None:  # pragma: no cover
        pass
