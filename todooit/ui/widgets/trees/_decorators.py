from functools import partial
from typing import TYPE_CHECKING, Any, Callable

from textual.widgets.option_list import OptionDoesNotExist

from todooit.api.exceptions import NoNodeError
from todooit.ui.api.events import BarNotification, ShowConfirm

if TYPE_CHECKING:  # pragma: no cover
    from .model_tree import ModelTree


def fix_highlight(func: Callable) -> Callable:
    def wrapper(self: "ModelTree", *args, **kwargs) -> Any:
        highlighted_id = self.node.id if self.highlighted is not None else None
        highlighted_index = self.highlighted

        func(self, *args, **kwargs)

        try:
            if highlighted_id is None:
                self.highlighted = highlighted_index
                self._ensure_enabled_highlight()
            else:
                self.highlight_id(highlighted_id)

        except OptionDoesNotExist:
            # Row is gone; fall back to its index, which may now be a rule/heading
            self.highlighted = highlighted_index
            self._ensure_enabled_highlight()

    return wrapper


def refresh_tree(func: Callable) -> Callable:
    def wrapper(self: "ModelTree", *args, **kwargs) -> Any:
        res = func(self, *args, **kwargs)
        self.force_refresh()
        return res

    return wrapper


def require_highlighted_node(func: Callable) -> Callable:
    def wrapper(self: "ModelTree", *args, **kwargs) -> Any:
        if self.highlighted is None:
            raise NoNodeError()

        return func(self, *args, **kwargs)

    return wrapper


def reject_fixed_node(message: str) -> Callable:
    """Rejects the edit when the cursor is on a fixed (non-database) project, warning with `message`."""

    def decorator(func: Callable) -> Callable:
        def wrapper(self: "ModelTree", *args, **kwargs) -> Any:
            if self.is_fixed_node:
                self.post_message(
                    BarNotification(
                        message.format(self.current_model.description), "warning"
                    )
                )
                return

            return func(self, *args, **kwargs)

        return wrapper

    return decorator


def require_confirmation(func: Callable) -> Callable:
    """Asks y/N before an irreversible edit; the question is built before running it, since the row it names may disappear after."""

    def wrapper(self: "ModelTree", *args, **kwargs) -> Any:
        question, confirmed, cancelled = self.delete_confirmation()
        function = partial(func, self, *args, **kwargs)

        if not self.api.vars.show_confirm:
            result = function()
            self.post_message(BarNotification(confirmed, "warning"))
            return result

        self.post_message(ShowConfirm(function, question, confirmed, cancelled))

    return wrapper
