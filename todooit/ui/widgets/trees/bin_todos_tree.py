from .fixed_todos_tree import FixedTodosTree


class BinTodosTree(FixedTodosTree):
    """
    The Bin: fixed pane of discarded tasks, newest first, each row showing its origin project.

    Nothing here can be ticked off — only restored or deleted for good.
    """

    # A binned task can't be worked on, so it can't be broken into new steps either
    takes_new_steps = False

    def goto_item(self) -> None:
        """Can't go to the source project — it may no longer exist; restoring is what takes the cursor there."""

        self._not_here(
            "Tasks can't be gone to",
            "[b]u[/b] restores one and goes with it",
        )

    def toggle_complete(self):
        self._not_here("Tasks can't be ticked off")
