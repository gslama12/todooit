class TodooitError(Exception):
    """
    Base class for all exceptions raised by the API.
    """


class NoParentError(TodooitError):
    """
    Raised when user tries to add a Todo object without a parent
    """


class MultipleParentError(TodooitError):
    """
    Raised when user tries to add a Todo object with both a project and a todo parent
    """


class NoNodeError(TodooitError):
    """
    Raised when user tried to perform an operation that requires a node, but no node is selected
    """

    def __str__(self) -> str:  # pragma: no cover
        return "No item selected"
