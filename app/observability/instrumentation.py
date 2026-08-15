from collections.abc import Callable
from functools import wraps
from typing import ParamSpec, TypeVar

from app.observability.metrics import safe_metric

P = ParamSpec("P")
R = TypeVar("R")


def observe_handoff(operation: str) -> Callable[[Callable[P, R]], Callable[P, R]]:
    def decorator(function: Callable[P, R]) -> Callable[P, R]:
        @wraps(function)
        def wrapped(*args: P.args, **kwargs: P.kwargs) -> R:
            try:
                result = function(*args, **kwargs)
            except Exception:
                safe_metric("record_handoff", operation, "failure")
                raise
            safe_metric("record_handoff", operation, "success")
            return result

        return wrapped

    return decorator


def observe_conversation(
    operation: str,
) -> Callable[[Callable[P, R]], Callable[P, R]]:
    def decorator(function: Callable[P, R]) -> Callable[P, R]:
        @wraps(function)
        def wrapped(*args: P.args, **kwargs: P.kwargs) -> R:
            try:
                result = function(*args, **kwargs)
            except Exception:
                safe_metric("record_conversation", operation, "failure")
                raise
            safe_metric("record_conversation", operation, "success")
            return result

        return wrapped

    return decorator
