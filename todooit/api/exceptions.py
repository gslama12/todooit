class DooitError(Exception):
    """
    Base class for all exceptions raised by the API.
    """


class NoParentError(DooitError):
    """
    Raised when user tries to add a Todo object without a parent
    """


class MultipleParentError(DooitError):
    """
    Raised when user tries to add a Todo object with both a project and a todo parent
    """


class NoNodeError(DooitError):
    """
    Raised when user tried to perform an operation that requires a node, but no node is selected
    """

    def __str__(self) -> str:  # pragma: no cover
        return "No item selected"
