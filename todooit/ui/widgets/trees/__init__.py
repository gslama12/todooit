from .bin_todos_tree import BinTodosTree
from .completed_todos_tree import CompletedTodosTree
from .fixed_todos_tree import FixedTodosTree
from .projects_tree import ProjectsTree
from .todos_tree import TodosTree


def make_todos_tree(project) -> TodosTree:
    """Picks the tasks-pane class matching a project's kind (stored, bin, completed, other fixed)."""

    if not getattr(project, "is_fixed", False):
        return TodosTree(project)

    if getattr(project, "gathers_binned", False):
        return BinTodosTree(project)

    if getattr(project, "sends_unticked_home", False):
        return CompletedTodosTree(project)

    return FixedTodosTree(project)


__all__ = [
    "TodosTree",
    "FixedTodosTree",
    "BinTodosTree",
    "CompletedTodosTree",
    "ProjectsTree",
    "make_todos_tree",
]
