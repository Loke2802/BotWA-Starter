from datetime import datetime
from typing import Annotated, NoReturn
from uuid import UUID

from fastapi import APIRouter, Depends, HTTPException, Query, status

from app.api.dashboard_dependencies import get_dashboard_query_service
from app.api.dependencies import require_permission
from app.application.dashboard.service import DashboardQueryService
from app.domain.dashboard.contracts import (
    DashboardPeriodPreset,
    DashboardSummaryResponse,
)
from app.domain.dashboard.errors import (
    DashboardError,
    DashboardForbidden,
    DashboardInvalidFilter,
    DashboardInvalidRange,
    DashboardNotFound,
    DashboardUnavailable,
)
from app.domain.user.contracts import User

router = APIRouter(
    prefix="/organizations/{organization_id}/dashboard", tags=["dashboard"]
)

PeriodQuery = Annotated[str | None, Query(alias="period")]
FromQuery = Annotated[datetime | None, Query(alias="from")]
ToQuery = Annotated[datetime | None, Query(alias="to")]


def _period(value: str | None) -> DashboardPeriodPreset | None:
    if value is None:
        return None
    if value == "today":
        return "today"
    if value == "last_7_days":
        return "last_7_days"
    if value == "last_30_days":
        return "last_30_days"
    raise DashboardInvalidFilter("dashboard period is invalid")


def _raise(exc: DashboardError) -> NoReturn:
    if isinstance(exc, DashboardNotFound):
        code = status.HTTP_404_NOT_FOUND
    elif isinstance(exc, DashboardForbidden):
        code = status.HTTP_403_FORBIDDEN
    elif isinstance(exc, (DashboardInvalidRange, DashboardInvalidFilter)):
        code = status.HTTP_422_UNPROCESSABLE_CONTENT
    elif isinstance(exc, DashboardUnavailable):
        code = status.HTTP_503_SERVICE_UNAVAILABLE
    else:
        code = status.HTTP_503_SERVICE_UNAVAILABLE
    raise HTTPException(status_code=code, detail={"code": exc.safe_code}) from exc


@router.get("", response_model=DashboardSummaryResponse)
def get_dashboard(
    organization_id: UUID,
    service: Annotated[DashboardQueryService, Depends(get_dashboard_query_service)],
    actor: Annotated[User, Depends(require_permission("dashboard.read"))],
    bot_id: UUID | None = None,
    period: PeriodQuery = None,
    from_: FromQuery = None,
    to: ToQuery = None,
) -> DashboardSummaryResponse:
    try:
        return service.summary(
            organization_id,
            actor,
            bot_id=bot_id,
            period=_period(period),
            from_=from_,
            to=to,
        )
    except DashboardError as exc:
        _raise(exc)
