from ..inputs.model_inputs import (
    Binned,
    Due,
    Note,
    Priority,
    Recurrence,
    Scheduled,
    Status,
    TodoDescription,
)
from .base_renderer import BaseRenderer, Todo


class TodoRender(BaseRenderer[Todo]):
    @property
    def model(self) -> Todo:
        return self._model

    def post_init(self):
        self.description = TodoDescription(self.model)
        self.due = Due(self.model)
        self.scheduled = Scheduled(self.model)
        self.binned = Binned(self.model)
        self.status = Status(self.model)
        self.priority = Priority(self.model)
        self.recurrence = Recurrence(self.model)
        self.note = Note(self.model)
