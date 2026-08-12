from datetime import date
from typing import Annotated, NoReturn
from uuid import UUID

from fastapi import APIRouter, Depends, HTTPException, Query, Response, status

from app.api.analytics_dependencies import get_analytics_query_service
from app.api.dependencies import require_permission
from app.api.plan_routes import raise_plan_error
from app.application.analytics.service import AnalyticsQueryService
from app.domain.analytics.contracts import (
    AnalyticsCompare,
    AnalyticsGroupBy,
    AnalyticsResponse,
)
from app.domain.analytics.errors import (
    AnalyticsDataIncomplete,
    AnalyticsError,
    AnalyticsForbidden,
    AnalyticsInvalidGrouping,
    AnalyticsInvalidRange,
    AnalyticsNotFound,
    AnalyticsRangeTooLarge,
)
from app.domain.plans.errors import PlanError
from app.domain.user.contracts import User

router = APIRouter(
    prefix="/organizations/{organization_id}/analytics", tags=["analytics"]
)

FromQuery = Annotated[date, Query(alias="from")]
ToQuery = Annotated[date, Query(alias="to")]


def _grouping(value: str) -> AnalyticsGroupBy:
    if value == "day":
        return "day"
    if value == "week":
        return "week"
    if value == "month":
        return "month"
    raise AnalyticsInvalidGrouping("analytics grouping is invalid")


def _comparison(value: str | None) -> AnalyticsCompare | None:
    if value is None:
        return None
    if value == "previous_period":
        return "previous_period"
    raise AnalyticsInvalidGrouping("analytics comparison is invalid")


def _raise(exc: AnalyticsError) -> NoReturn:
    if isinstance(exc, AnalyticsNotFound):
        code = status.HTTP_404_NOT_FOUND
    elif isinstance(exc, AnalyticsForbidden):
        code = status.HTTP_403_FORBIDDEN
    elif isinstance(exc, AnalyticsDataIncomplete):
        code = status.HTTP_409_CONFLICT
    elif isinstance(
        exc, (AnalyticsInvalidRange, AnalyticsRangeTooLarge, AnalyticsInvalidGrouping)
    ):
        code = status.HTTP_422_UNPROCESSABLE_CONTENT
    else:
        code = status.HTTP_503_SERVICE_UNAVAILABLE
    raise HTTPException(status_code=code, detail={"code": exc.safe_code}) from exc


@router.get("", response_model=AnalyticsResponse)
def get_analytics(
    organization_id: UUID,
    service: Annotated[AnalyticsQueryService, Depends(get_analytics_query_service)],
    actor: Annotated[User, Depends(require_permission("analytics.read"))],
    from_: FromQuery,
    to: ToQuery,
    bot_id: UUID | None = None,
    group_by: str = "day",
    compare: str | None = None,
) -> AnalyticsResponse:
    try:
        return service.query(
            organization_id,
            actor,
            bot_id=bot_id,
            from_=from_,
            to=to,
            group_by=_grouping(group_by),
            compare=_comparison(compare),
        )
    except PlanError as exc:
        raise_plan_error(exc)
    except AnalyticsError as exc:
        _raise(exc)


@router.get("/export")
def export_analytics(
    organization_id: UUID,
    service: Annotated[AnalyticsQueryService, Depends(get_analytics_query_service)],
    actor: Annotated[User, Depends(require_permission("analytics.export"))],
    from_: FromQuery,
    to: ToQuery,
    bot_id: UUID | None = None,
    group_by: str = "day",
    format_: Annotated[str, Query(alias="format")] = "csv",
) -> Response:
    try:
        if format_ != "csv":
            raise AnalyticsInvalidGrouping("analytics export format is invalid")
        content = service.export_csv(
            organization_id,
            actor,
            bot_id=bot_id,
            from_=from_,
            to=to,
            group_by=_grouping(group_by),
        )
        return Response(
            content=content,
            media_type="text/csv",
            headers={
                "Content-Disposition": "attachment; filename=analytics-report.csv"
            },
        )
    except PlanError as exc:
        raise_plan_error(exc)
    except AnalyticsError as exc:
        _raise(exc)
