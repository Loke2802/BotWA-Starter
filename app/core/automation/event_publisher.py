from datetime import UTC, datetime
from typing import Protocol, runtime_checkable
from uuid import UUID, uuid4

import structlog

from app.infrastructure.models.business_event import BusinessEventModel


@runtime_checkable
class HasAdd(Protocol):
    def add(self, event: BusinessEventModel) -> None: ...


class AutomationEventPublisher:
    def __init__(
        self,
        event_repository: HasAdd | None = None,
    ) -> None:
        self._logger = structlog.get_logger(__name__)
        self._event_repo = event_repository

    def publish(
        self,
        event_type: str,
        execution_id: UUID,
        **kwargs: object,
    ) -> None:
        self._logger.info("automation_event", event_type=event_type, **kwargs)
        if self._event_repo:
            payload: dict[str, object] = {
                "execution_id": str(execution_id),
            }
            payload.update(kwargs)
            event = BusinessEventModel(
                id=uuid4(),
                event_type=event_type,
                source="automation_engine",
                payload=payload,
                created_at=datetime.now(UTC),
            )
            self._event_repo.add(event)
