from datetime import datetime
from typing import Protocol
from uuid import UUID

from app.domain.automation_management.contracts import BusinessHoursState


class BusinessHoursStateProvider(Protocol):
    def state(
        self,
        organization_id: UUID,
        bot_id: UUID,
        occurred_at: datetime,
    ) -> BusinessHoursState: ...
