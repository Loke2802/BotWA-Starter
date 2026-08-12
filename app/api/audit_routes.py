from datetime import datetime
from typing import Annotated, NoReturn
from uuid import UUID

from fastapi import APIRouter, Depends, HTTPException, Query, status

from app.api.audit_dependencies import get_audit_query_service
from app.api.dependencies import require_authenticated_user
from app.api.plan_routes import raise_plan_error
from app.application.audit.service import AuditQueryService
from app.domain.audit.contracts import AuditEventListResponse
from app.domain.audit.errors import (
    AuditError,
    AuditForbidden,
    AuditInvalidCursor,
    AuditInvalidFilter,
    AuditInvalidRange,
    AuditRangeTooLarge,
)
from app.domain.plans.errors import PlanError
from app.domain.user.contracts import User

router = APIRouter(
    prefix="/organizations/{organization_id}/audit-events", tags=["audit"]
)


def _raise(exc: AuditError) -> NoReturn:
    if isinstance(exc, AuditForbidden):
        code = status.HTTP_403_FORBIDDEN
    elif isinstance(
        exc,
        (AuditInvalidCursor, AuditInvalidFilter, AuditInvalidRange, AuditRangeTooLarge),
    ):
        code = status.HTTP_422_UNPROCESSABLE_CONTENT
    else:
        code = status.HTTP_503_SERVICE_UNAVAILABLE
    raise HTTPException(status_code=code, detail={"code": exc.safe_code}) from exc


@router.get("", response_model=AuditEventListResponse)
def list_audit_events(
    organization_id: UUID,
    service: Annotated[AuditQueryService, Depends(get_audit_query_service)],
    actor: Annotated[User, Depends(require_authenticated_user)],
    actor_user_id: UUID | None = None,
    action: str | None = None,
    resource_type: str | None = None,
    resource_id: UUID | None = None,
    from_: Annotated[datetime | None, Query(alias="from")] = None,
    to: datetime | None = None,
    cursor: str | None = None,
    limit: int = 50,
) -> AuditEventListResponse:
    try:
        return service.query(
            organization_id,
            actor,
            actor_user_id=actor_user_id,
            action=action,
            resource_type=resource_type,
            resource_id=resource_id,
            from_=from_,
            to=to,
            cursor=cursor,
            limit=limit,
        )
    except PlanError as exc:
        raise_plan_error(exc)
    except AuditError as exc:
        _raise(exc)
