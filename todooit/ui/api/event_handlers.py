from typing import Callable, Type
from todooit.ui.api.events import TodooitEvent

TODOOIT_EVENT_ATTR = "__todooit_event"
TODOOIT_TIMER_ATTR = "__todooit_timer"


def subscribe(*events: Type[TodooitEvent]):
    """
    Subscribe decorator for event handlers
    """

    def decorator(func: Callable):
        attrs = getattr(func, TODOOIT_EVENT_ATTR, [])
        attrs.extend(events)

        setattr(func, TODOOIT_EVENT_ATTR, attrs)
        return func

    return decorator


def timer(interval: float):
    """
    Timer decorator for event handlers
    """

    def decorator(func: Callable):
        setattr(func, TODOOIT_TIMER_ATTR, interval)
        return func

    return decorator
