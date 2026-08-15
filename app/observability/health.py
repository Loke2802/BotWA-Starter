from dataclasses import dataclass
from math import ceil

from sqlalchemy import Engine, create_engine, text
from sqlalchemy.exc import SQLAlchemyError
from sqlalchemy.pool import NullPool


@dataclass(frozen=True)
class ReadinessResult:
    ready: bool


class DatabaseReadinessProbe:
    """Isolated bounded probe; it never consumes the application pool."""

    def __init__(
        self, database_url: str, *, timeout_seconds: float, enabled: bool = True
    ) -> None:
        self.enabled = enabled
        self.timeout_seconds = timeout_seconds
        connect_args: dict[str, object] = {}
        if database_url.startswith("postgresql"):
            connect_args = {
                "connect_timeout": max(1, ceil(timeout_seconds)),
                "options": (
                    f"-c statement_timeout=" f"{max(1, int(timeout_seconds * 1000))}"
                ),
            }
        self.engine: Engine = create_engine(
            database_url,
            poolclass=NullPool,
            connect_args=connect_args,
        )

    def check(self) -> ReadinessResult:
        if not self.enabled:
            return ReadinessResult(ready=True)
        try:
            with self.engine.connect() as connection:
                connection.execute(text("SELECT 1"))
        except SQLAlchemyError:
            return ReadinessResult(ready=False)
        return ReadinessResult(ready=True)

    def close(self) -> None:
        self.engine.dispose()
