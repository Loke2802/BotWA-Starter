from typing import Annotated, NoReturn
from uuid import UUID

from fastapi import APIRouter, Depends, HTTPException, Query, status

from app.api.automation_management_dependencies import get_managed_automation_service
from app.api.dependencies import require_permission
from app.application.automation_management.service import (
    AutomationConflictError,
    AutomationNotFoundError,
    ManagedAutomationService,
)
from app.domain.automation_management.contracts import (
    AutomationDefinitionInput,
    AutomationDefinitionListResponse,
    AutomationDefinitionResponse,
    AutomationDefinitionUpdate,
    AutomationExecutionListResponse,
    AutomationExecutionResponse,
)
from app.domain.user.contracts import User

router = APIRouter(
    prefix="/organizations/{organization_id}", tags=["automation-management"]
)


def _raise(exc: ValueError) -> NoReturn:
    code = (
        status.HTTP_404_NOT_FOUND
        if isinstance(exc, AutomationNotFoundError)
        else (
            status.HTTP_409_CONFLICT
            if isinstance(exc, AutomationConflictError)
            else status.HTTP_403_FORBIDDEN
        )
    )
    raise HTTPException(status_code=code, detail=str(exc)) from exc


@router.post(
    "/automations",
    response_model=AutomationDefinitionResponse,
    status_code=status.HTTP_201_CREATED,
)
def create(
    organization_id: UUID,
    payload: AutomationDefinitionInput,
    service: Annotated[
        ManagedAutomationService, Depends(get_managed_automation_service)
    ],
    actor: Annotated[User, Depends(require_permission("automation.create"))],
):
    try:
        return service.create(organization_id, payload, actor)
    except ValueError as exc:
        _raise(exc)


@router.get("/automations", response_model=AutomationDefinitionListResponse)
def list_definitions(
    organization_id: UUID,
    service: Annotated[
        ManagedAutomationService, Depends(get_managed_automation_service)
    ],
    actor: Annotated[User, Depends(require_permission("automation.read"))],
    status_filter: str | None = Query(None, alias="status"),
    bot_id: UUID | None = None,
    trigger_type: str | None = None,
    page: int = Query(1, ge=1),
    page_size: int = Query(20, ge=1, le=100),
):
    try:
        items, total = service.list(
            organization_id,
            actor,
            status=status_filter,
            bot_id=bot_id,
            trigger_type=trigger_type,
            offset=(page - 1) * page_size,
            limit=page_size,
        )
        return AutomationDefinitionListResponse(
            items=items,
            total=total,
            page=page,
            page_size=page_size,
            has_next=page * page_size < total,
        )
    except ValueError as exc:
        _raise(exc)


@router.get("/automations/{automation_id}", response_model=AutomationDefinitionResponse)
def get_definition(
    organization_id: UUID,
    automation_id: UUID,
    service: Annotated[
        ManagedAutomationService, Depends(get_managed_automation_service)
    ],
    actor: Annotated[User, Depends(require_permission("automation.read"))],
):
    try:
        return service.get(organization_id, automation_id, actor)
    except ValueError as exc:
        _raise(exc)


@router.patch(
    "/automations/{automation_id}", response_model=AutomationDefinitionResponse
)
def update(
    organization_id: UUID,
    automation_id: UUID,
    payload: AutomationDefinitionUpdate,
    service: Annotated[
        ManagedAutomationService, Depends(get_managed_automation_service)
    ],
    actor: Annotated[User, Depends(require_permission("automation.update"))],
):
    try:
        return service.update(
            organization_id,
            automation_id,
            payload.model_dump(exclude_unset=True),
            actor,
        )
    except ValueError as exc:
        _raise(exc)


def _transition(target: str):
    def action(
        organization_id: UUID,
        automation_id: UUID,
        service: Annotated[
            ManagedAutomationService, Depends(get_managed_automation_service)
        ],
        actor: Annotated[User, Depends(require_permission(f"automation.{target}"))],
    ):
        try:
            return service.transition(organization_id, automation_id, target, actor)
        except ValueError as exc:
            _raise(exc)

    return action


router.post(
    "/automations/{automation_id}/activate", response_model=AutomationDefinitionResponse
)(_transition("activate"))
router.post(
    "/automations/{automation_id}/deactivate",
    response_model=AutomationDefinitionResponse,
)(_transition("deactivate"))
router.post(
    "/automations/{automation_id}/archive", response_model=AutomationDefinitionResponse
)(_transition("archive"))


@router.get(
    "/automations/{automation_id}/executions",
    response_model=AutomationExecutionListResponse,
)
def list_executions(
    organization_id: UUID,
    automation_id: UUID,
    service: Annotated[
        ManagedAutomationService, Depends(get_managed_automation_service)
    ],
    actor: Annotated[User, Depends(require_permission("automation.executions.read"))],
    page: int = Query(1, ge=1),
    page_size: int = Query(20, ge=1, le=100),
):
    try:
        service.get(organization_id, automation_id, actor)
        items, total = service.repo.executions(
            organization_id,
            automation_id,
            offset=(page - 1) * page_size,
            limit=page_size,
        )
        return AutomationExecutionListResponse(
            items=items,
            total=total,
            page=page,
            page_size=page_size,
            has_next=page * page_size < total,
        )
    except ValueError as exc:
        _raise(exc)


@router.get(
    "/automation-executions/{execution_id}", response_model=AutomationExecutionResponse
)
def get_execution(
    organization_id: UUID,
    execution_id: UUID,
    service: Annotated[
        ManagedAutomationService, Depends(get_managed_automation_service)
    ],
    actor: Annotated[User, Depends(require_permission("automation.executions.read"))],
):
    try:
        service._auth(actor, "automation.executions.read", organization_id)
        row = service.repo.execution(organization_id, execution_id)
        if row is None:
            raise AutomationNotFoundError("automation execution not found")
        return row
    except ValueError as exc:
        _raise(exc)


@router.post(
    "/automation-executions/{execution_id}/retry",
    response_model=AutomationExecutionResponse,
)
def retry(
    organization_id: UUID,
    execution_id: UUID,
    service: Annotated[
        ManagedAutomationService, Depends(get_managed_automation_service)
    ],
    actor: Annotated[User, Depends(require_permission("automation.executions.retry"))],
):
    try:
        service._auth(actor, "automation.executions.retry", organization_id)
        row = service.repo.execution(organization_id, execution_id, lock=True)
        if row is None:
            raise AutomationNotFoundError("automation execution not found")
        if row.status != "failed" or row.attempt_count >= 3:
            raise AutomationConflictError("execution cannot be retried")
        from datetime import UTC, datetime

        row.status, row.available_at, row.safe_error_code = (
            "pending",
            datetime.now(UTC),
            None,
        )
        service.session.commit()
        return row
    except ValueError as exc:
        _raise(exc)
