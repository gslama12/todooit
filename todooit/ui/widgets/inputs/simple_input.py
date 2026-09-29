from typing import Any, Generic, TypeVar

from todooit.api import TodooitModel
from ._input import Input

ModelType = TypeVar("ModelType", bound=TodooitModel)
ModelValue = TypeVar("ModelValue", bound=Any)


class SimpleInput(Input, Generic[ModelType, ModelValue]):
    """A simple single line Text Input widget."""

    def __init__(self, model: ModelType) -> None:
        self.model = model

        default_value = self._get_default_value()
        super().__init__(value=default_value)

    def _get_default_value(self) -> str:
        return str(self.model_value)

    @property
    def _property(self) -> str:
        return self.__class__.__name__.lower()

    @property
    def model_value(self) -> ModelValue:
        return getattr(self.model, self._property)

    @model_value.setter
    def model_value(self, value: str) -> None:
        return setattr(self.model, self._property, value)

    def _typecast_value(self, value: str) -> Any:
        return value

    def start_edit(self) -> None:
        """
        Refill the buffer from the model before editing, in case the model
        changed since the renderer was built (e.g. an external update).
        """

        self._value = self._get_default_value()
        super().start_edit()
        self.move_cursor_to_end()

    def stop_edit(self, cancel: bool = False) -> None:
        """End the edit, writing the buffer to the model unless cancelled."""

        if cancel:
            self._value = self._get_default_value()
            super().stop_edit(cancel)
            self.move_cursor_to_end()
            return

        self._value = self.value.strip()
        try:
            self.model_value = self._typecast_value(self.value)
            self.model.save()
        finally:
            self._value = self._get_default_value()
            super().stop_edit()
            self.move_cursor_to_end()
