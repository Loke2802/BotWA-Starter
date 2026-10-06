from collections.abc import Generator
from typing import Annotated
from uuid import UUID

from fastapi import APIRouter, Depends, Header, HTTPException, Query
from sqlalchemy.exc import SQLAlchemyError

from app.api.crm_routes import Actor
from app.api.whatsapp_configuration_dependencies import get_whatsapp_secret_cipher
from app.application.crm.service import OpportunityService
from app.domain.crm.contracts import (
    CommercialContext,
    CrmConflict,
    CrmNotFound,
    HistoryRecord,
    OpportunityCreate,
    OpportunityList,
    OpportunityRecord,
    OpportunityUpdate,
    Stage,
    StageConfiguration,
)
from app.infrastructure.database import get_session
from app.infrastructure.settings import get_settings
from app.security.authorization import AuthorizationError

router = APIRouter(
    prefix="/organizations/{organization_id}", tags=["crm-opportunities"]
)


def get_opportunity_service() -> Generator[OpportunityService]:
    sessions = get_session()
    session = next(sessions)
    try:
        yield OpportunityService(
            session,
            get_whatsapp_secret_cipher(),
            get_settings().contact_identity_hmac_key,
        )
    finally:
        sessions.close()


Service = Annotated[OpportunityService, Depends(get_opportunity_service)]


def fail(exc: Exception) -> HTTPException:
    if isinstance(exc, AuthorizationError):
        return HTTPException(403, "No tienes permiso para esta acción.")
    if isinstance(exc, CrmNotFound):
        return HTTPException(404, "No encontramos el recurso en tu empresa.")
    if isinstance(exc, CrmConflict):
        return HTTPException(409, str(exc))
    if isinstance(exc, SQLAlchemyError):
        return HTTPException(
            503, "No se pudo confirmar la operación. Reintenta con la misma clave."
        )
    return HTTPException(400, "Revisa etapa, responsable y próxima acción.")


@router.get(
    "/conversations/{conversation_id}/commercial-context",
    response_model=CommercialContext,
)
def context(
    organization_id: UUID, conversation_id: UUID, actor: Actor, service: Service
) -> CommercialContext:
    try:
        return service.context(organization_id, conversation_id, actor)
    except (ValueError, SQLAlchemyError) as exc:
        raise fail(exc) from exc


@router.get("/crm/stages", response_model=list[Stage])
def stages(organization_id: UUID, actor: Actor, service: Service) -> list[Stage]:
    try:
        return service.stages(organization_id, actor)
    except (ValueError, SQLAlchemyError) as exc:
        raise fail(exc) from exc


@router.put("/crm/stages", response_model=list[Stage])
def configure(
    organization_id: UUID, data: StageConfiguration, actor: Actor, service: Service
) -> list[Stage]:
    try:
        return service.configure_stages(organization_id, actor, data)
    except (ValueError, SQLAlchemyError) as exc:
        raise fail(exc) from exc


@router.get("/crm/opportunities", response_model=OpportunityList)
def opportunities(
    organization_id: UUID,
    actor: Actor,
    service: Service,
    contact_id: UUID | None = None,
    conversation_id: UUID | None = None,
    assigned_user_id: UUID | None = None,
    stage_code: str | None = Query(default=None, max_length=40),
    page: int = Query(default=1, ge=1),
    page_size: int = Query(default=20, ge=1, le=100),
) -> OpportunityList:
    try:
        return service.list_opportunities(
            organization_id,
            actor,
            contact_id=contact_id,
            conversation_id=conversation_id,
            assigned_user_id=assigned_user_id,
            stage_code=stage_code,
            page=page,
            page_size=page_size,
        )
    except (ValueError, SQLAlchemyError) as exc:
        raise fail(exc) from exc


@router.post("/crm/opportunities", response_model=OpportunityRecord, status_code=201)
def create(
    organization_id: UUID,
    data: OpportunityCreate,
    actor: Actor,
    service: Service,
    key: Annotated[
        str,
        Header(
            alias="Idempotency-Key",
            min_length=1,
            max_length=128,
            pattern=r"^[A-Za-z0-9_-]+$",
        ),
    ],
) -> OpportunityRecord:
    try:
        return service.create(organization_id, actor, data, key)
    except (ValueError, SQLAlchemyError) as exc:
        raise fail(exc) from exc


@router.get("/crm/opportunities/{opportunity_id}", response_model=OpportunityRecord)
def detail(
    organization_id: UUID, opportunity_id: UUID, actor: Actor, service: Service
) -> OpportunityRecord:
    try:
        return service.get(organization_id, opportunity_id, actor)
    except (ValueError, SQLAlchemyError) as exc:
        raise fail(exc) from exc


@router.patch("/crm/opportunities/{opportunity_id}", response_model=OpportunityRecord)
def update(
    organization_id: UUID,
    opportunity_id: UUID,
    data: OpportunityUpdate,
    actor: Actor,
    service: Service,
) -> OpportunityRecord:
    try:
        return service.update(organization_id, opportunity_id, actor, data)
    except (ValueError, SQLAlchemyError) as exc:
        raise fail(exc) from exc


@router.put(
    "/crm/opportunities/{opportunity_id}/conversations/{conversation_id}",
    response_model=OpportunityRecord,
)
def link(
    organization_id: UUID,
    opportunity_id: UUID,
    conversation_id: UUID,
    actor: Actor,
    service: Service,
) -> OpportunityRecord:
    try:
        return service.link(organization_id, opportunity_id, conversation_id, actor)
    except (ValueError, SQLAlchemyError) as exc:
        raise fail(exc) from exc


@router.get(
    "/crm/opportunities/{opportunity_id}/history", response_model=list[HistoryRecord]
)
def history(
    organization_id: UUID,
    opportunity_id: UUID,
    actor: Actor,
    service: Service,
    page: int = Query(default=1, ge=1),
    page_size: int = Query(default=20, ge=1, le=100),
) -> list[HistoryRecord]:
    try:
        return service.history(organization_id, opportunity_id, actor, page, page_size)
    except (ValueError, SQLAlchemyError) as exc:
        raise fail(exc) from exc
