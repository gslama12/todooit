from ..inputs.model_inputs import ProjectDescription
from .base_renderer import BaseRenderer, Project


class ProjectRender(BaseRenderer[Project]):
    @property
    def model(self) -> Project:
        return self._model

    def post_init(self):
        self.description = ProjectDescription(self.model)
