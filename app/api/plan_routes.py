from typing import Annotated, NoReturn
from uuid import UUID

from fastapi import APIRouter, Depends, HTTPException, status

from app.api.dependencies import require_authenticated_user
from app.api.plan_dependencies import (
    get_plan_assignment_service,
    get_plan_query_service,
)
from app.application.plans.service import PlanAssignmentService, PlanQueryService
from app.domain.plans.contracts import OrganizationPlanResponse, PlanAssignmentRequest
from app.domain.plans.errors import (
    PlanAssignmentNotFound,
    PlanError,
    PlanFeatureNotAvailable,
    PlanForbidden,
    PlanLimitReached,
    PlanNotFound,
    PlanVersionConflict,
)
from app.domain.user.contracts import User

router = APIRouter(prefix="/organizations/{organization_id}/plan", tags=["plans"])


def raise_plan_error(exc: PlanError) -> NoReturn:
    if isinstance(exc, (PlanForbidden, PlanFeatureNotAvailable)):
        code = status.HTTP_403_FORBIDDEN
    elif isinstance(exc, (PlanNotFound, PlanAssignmentNotFound)):
        code = status.HTTP_404_NOT_FOUND
    elif isinstance(exc, (PlanVersionConflict, PlanLimitReached)):
        code = status.HTTP_409_CONFLICT
    else:
        code = status.HTTP_503_SERVICE_UNAVAILABLE
    detail: dict[str, str] = {"code": exc.safe_code}
    if isinstance(exc, PlanLimitReached):
        detail["limit_key"] = exc.limit_key
    raise HTTPException(status_code=code, detail=detail) from exc


@router.get("", response_model=OrganizationPlanResponse)
def get_organization_plan(
    organization_id: UUID,
    service: Annotated[PlanQueryService, Depends(get_plan_query_service)],
    actor: Annotated[User, Depends(require_authenticated_user)],
) -> OrganizationPlanResponse:
    try:
        return service.get(organization_id, actor)
    except PlanError as exc:
        raise_plan_error(exc)


@router.put("", response_model=OrganizationPlanResponse)
def assign_organization_plan(
    organization_id: UUID,
    request: PlanAssignmentRequest,
    service: Annotated[PlanAssignmentService, Depends(get_plan_assignment_service)],
    actor: Annotated[User, Depends(require_authenticated_user)],
) -> OrganizationPlanResponse:
    try:
        return service.assign(
            organization_id,
            request.plan_code,
            request.expected_version,
            actor,
        )
    except PlanError as exc:
        raise_plan_error(exc)
