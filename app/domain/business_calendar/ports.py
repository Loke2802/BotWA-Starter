from collections.abc import Sequence
from datetime import datetime
from typing import Protocol
from uuid import UUID

from app.domain.business_calendar.contracts import ImportedCalendarRule


class Clock(Protocol):
    def now(self) -> datetime: ...


class ExternalCalendarAdapter(Protocol):
    """Future provider boundary; PRD-015 ships without an implementation."""

    provider: str

    def import_rules(
        self,
        *,
        organization_id: UUID,
        connection_id: UUID,
        starts_at: datetime,
        ends_at: datetime,
    ) -> Sequence[ImportedCalendarRule]: ...
