from typing import TYPE_CHECKING, Any, Generic, Optional, TypeVar

from todooit.api import TodooitModel

if TYPE_CHECKING:  # pragma: no cover
    from todooit.api.lifecycle import Outcome
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

    def _write(self, value: Any) -> Optional["Outcome"]:
        """
        Store a typed value on the model

        A column whose field belongs to the lifecycle overrides this to go
        through it, and returns what the change meant.
        """

        self.model_value = value
        self.model.save()
        return None

    def start_edit(self) -> None:
        """
        Refill the buffer from the model before editing, in case the model
        changed since the renderer was built (e.g. an external update).
        """

        self._value = self._get_default_value()
        super().start_edit()
        self.move_cursor_to_end()

    def stop_edit(self, cancel: bool = False) -> Optional["Outcome"]:
        """
        End the edit, writing the buffer to the model unless cancelled

        Returns the lifecycle's outcome when the column goes through it.
        """

        if cancel:
            self._value = self._get_default_value()
            super().stop_edit(cancel)
            self.move_cursor_to_end()
            return None

        self._value = self.value.strip()
        try:
            return self._write(self._typecast_value(self.value))
        finally:
            self._value = self._get_default_value()
            super().stop_edit()
            self.move_cursor_to_end()
