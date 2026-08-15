from collections.abc import Iterator
from contextlib import contextmanager
from contextvars import ContextVar, Token
from uuid import UUID, uuid4

import structlog

_correlation_id: ContextVar[UUID | None] = ContextVar(
    "botwa_correlation_id", default=None
)


def normalized_correlation_id(value: str | None) -> UUID:
    if value is not None:
        try:
            return UUID(value)
        except (ValueError, AttributeError):
            pass
    return uuid4()


def current_correlation_id() -> UUID | None:
    return _correlation_id.get()


def bind_correlation_id(correlation_id: UUID) -> Token[UUID | None]:
    structlog.contextvars.bind_contextvars(correlation_id=str(correlation_id))
    return _correlation_id.set(correlation_id)


def clear_correlation_id(token: Token[UUID | None]) -> None:
    _correlation_id.reset(token)
    structlog.contextvars.clear_contextvars()


@contextmanager
def correlation_context(correlation_id: UUID | None = None) -> Iterator[UUID]:
    effective = correlation_id or uuid4()
    token = bind_correlation_id(effective)
    try:
        yield effective
    finally:
        clear_correlation_id(token)
