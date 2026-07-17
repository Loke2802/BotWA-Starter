from datetime import UTC, datetime
from uuid import uuid4

import structlog

from app.infrastructure.models.business_event import BusinessEventModel
from app.infrastructure.repositories.business_event_repository import (
    BusinessEventRepository,
)


class BusinessEventPublisher:
    def __init__(
        self,
        event_repository: BusinessEventRepository | None = None,
    ) -> None:
        self._logger = structlog.get_logger(__name__)
        self._event_repo = event_repository

    def publish(self, event_type: str, **kwargs: str | bool) -> None:
        self._logger.info("business_event", event_type=event_type, **kwargs)
        if self._event_repo:
            event = BusinessEventModel(
                id=uuid4(),
                event_type=event_type,
                source="business_brain",
                payload=kwargs,
                created_at=datetime.now(UTC),
            )
            self._event_repo.add(event)
