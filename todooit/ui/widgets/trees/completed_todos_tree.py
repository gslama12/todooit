from todooit.api import Todo, revive_home
from todooit.ui.api.events import RevealTodo
from .fixed_todos_tree import FixedTodosTree


def family_root(todo: Todo) -> Todo:
    """The top-level task a todo belongs to: itself, or whatever it's a step of."""

    node = todo

    while node.parent_todo is not None:
        node = node.parent_todo

    return node


class CompletedTodosTree(FixedTodosTree):
    """
    The completion log: fixed pane of finished tasks, with their finished steps drawn underneath.

    Unticking a task removes it from here (there is work left, so it doesn't belong
    in a "done" log) and follows it back to its project: reopens it, highlights
    the task, and flashes the row that was actually unticked (which may be a step,
    not the family root).
    """

    # A finished task can't gain new steps until it's unticked and back in play
    takes_new_steps = False

    def goto_item(self) -> None:
        """Can't go anywhere else — a finished task's own project no longer draws it; unticking does, and takes the cursor there."""

        self._not_here(
            "Tasks can't be gone to",
            "[b]c[/b] unticks one and goes with it",
        )

    def toggle_complete(self):
        todo = self.current_model
        assert isinstance(todo, Todo)

        super().toggle_complete()

        root = family_root(todo)

        # Ticked off again rather than unticked: stays in the log
        if not root.is_pending:
            return

        # Its project may have been dropped while it sat here; rebuild it to
        # give the now-pending task somewhere to live
        self.announce_revived(revive_home(root))

        self.post_message(RevealTodo(todo))
