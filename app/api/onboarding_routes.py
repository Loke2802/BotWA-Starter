from typing import Annotated, NoReturn
from uuid import UUID

from fastapi import APIRouter, Depends, HTTPException, status

from app.api.dependencies import require_authenticated_user
from app.api.onboarding_dependencies import get_onboarding_service
from app.application.onboarding.service import OnboardingService
from app.domain.onboarding.contracts import (
    OnboardingCompleteRequest,
    OnboardingResponse,
)
from app.domain.onboarding.errors import (
    OnboardingError,
    OnboardingForbidden,
    OnboardingNotReady,
    OnboardingNotStarted,
    OnboardingOrganizationNotFound,
    OnboardingUnavailable,
    OnboardingVersionConflict,
)
from app.domain.user.contracts import User

router = APIRouter(
    prefix="/organizations/{organization_id}/onboarding", tags=["onboarding"]
)


def raise_onboarding_error(exc: OnboardingError) -> NoReturn:
    if isinstance(exc, OnboardingOrganizationNotFound):
        code = status.HTTP_404_NOT_FOUND
    elif isinstance(exc, OnboardingForbidden):
        code = status.HTTP_403_FORBIDDEN
    elif isinstance(
        exc,
        (OnboardingNotStarted, OnboardingNotReady, OnboardingVersionConflict),
    ):
        code = status.HTTP_409_CONFLICT
    elif isinstance(exc, OnboardingUnavailable):
        code = status.HTTP_503_SERVICE_UNAVAILABLE
    else:
        code = status.HTTP_422_UNPROCESSABLE_ENTITY
    detail: dict[str, object] = {"code": exc.safe_code}
    if isinstance(exc, OnboardingNotReady):
        detail["blocking_reasons"] = list(exc.blockers)
    raise HTTPException(status_code=code, detail=detail) from exc


@router.get("", response_model=OnboardingResponse)
def get_onboarding(
    organization_id: UUID,
    service: Annotated[OnboardingService, Depends(get_onboarding_service)],
    actor: Annotated[User, Depends(require_authenticated_user)],
) -> OnboardingResponse:
    try:
        return service.get(organization_id, actor)
    except OnboardingError as exc:
        raise_onboarding_error(exc)


@router.post("/start", response_model=OnboardingResponse)
def start_onboarding(
    organization_id: UUID,
    service: Annotated[OnboardingService, Depends(get_onboarding_service)],
    actor: Annotated[User, Depends(require_authenticated_user)],
) -> OnboardingResponse:
    try:
        return service.start(organization_id, actor)
    except OnboardingError as exc:
        raise_onboarding_error(exc)


@router.post("/complete", response_model=OnboardingResponse)
def complete_onboarding(
    organization_id: UUID,
    request: OnboardingCompleteRequest,
    service: Annotated[OnboardingService, Depends(get_onboarding_service)],
    actor: Annotated[User, Depends(require_authenticated_user)],
) -> OnboardingResponse:
    try:
        return service.complete(organization_id, request.expected_version, actor)
    except OnboardingError as exc:
        raise_onboarding_error(exc)
