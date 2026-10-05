from todooit.api import Todo
from todooit.api.placement import root_of
from todooit.ui.api.events import RevealTodo
from .fixed_todos_tree import FixedTodosTree


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

        root = root_of(todo)

        # Ticked off again rather than unticked: stays in the log
        if not root.is_pending:
            return

        self.post_message(RevealTodo(todo))
