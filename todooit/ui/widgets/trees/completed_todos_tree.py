from todooit.api import Todo, revive_home
from todooit.ui.api.events import RevealTodo
from .fixed_todos_tree import FixedTodosTree


def family_root(todo: Todo) -> Todo:
    """
    The task a todo belongs to: itself, or whatever it is a step of
    """

    node = todo

    while node.parent_todo is not None:
        node = node.parent_todo

    return node


class CompletedTodosTree(FixedTodosTree):
    """
    The pane of a fixed project whose rows are the tasks already done

    A row here is a whole task: one finished todo, with the steps that were
    finished along with it drawn underneath it the way its own project drew
    them. Nothing arrives on its own until the whole of it is done.

    Unticking a todo anywhere else takes it out of the pane it was in and puts
    it back among the work still to do, and it does the same here — the row
    goes the moment the tick comes off, since there is work left in the task
    and this is the log of the ones there is not.

    What the pane adds is following it: the row is gone from in front of the
    cursor, so the app moves to where the row went. The project it was filed
    under is opened, the cursor lands on the task, and the row flashes, the
    same arrival the finder makes. Whichever row of a family was unticked, the
    whole of it comes back — unticking a step is unticking the task — and it
    is the row that was actually unticked that is pointed at.
    """

    def toggle_complete(self):
        todo = self.current_model
        assert isinstance(todo, Todo)

        super().toggle_complete()

        root = family_root(todo)

        # Ticked off again rather than unticked: a completed task like any
        # other from here on, and it was never going anywhere
        if not root.is_pending:
            return

        # A finished task can sit in the log with no project at all: the one it
        # was filed under was thrown away while it was in here. The moment
        # there is work left in it again it needs somewhere to be done, so the
        # project it names is built back to take it
        self.announce_revived(revive_home(root))

        self.post_message(RevealTodo(todo))
