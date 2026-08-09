from typing import Protocol

from app.domain.audit.contracts import (
    AuditCursor,
    AuditEventDraft,
    AuditEventResponse,
    AuditQuery,
)


class AuditWriter(Protocol):
    """Append an event to the caller-owned transaction; never commit."""

    def append(self, draft: AuditEventDraft) -> None: ...


class AuditReader(Protocol):
    def page(
        self, query: AuditQuery
    ) -> tuple[list[AuditEventResponse], AuditCursor | None]: ...
