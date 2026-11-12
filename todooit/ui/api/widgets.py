from enum import Enum
from typing import List


class ProjectWidget(Enum):
    description = "description"


class TodoWidget(Enum):
    description = "description"
    due = "due"
    scheduled = "scheduled"
    # When the todo was thrown away; only ever drawn by the Bin
    binned = "binned"
    priority = "priority"
    recurrence = "recurrence"
    status = "status"
    note = "note"


ProjectLayout = List[ProjectWidget]
TodoLayout = List[TodoWidget]
