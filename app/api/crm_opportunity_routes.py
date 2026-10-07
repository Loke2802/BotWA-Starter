from datetime import datetime
from typing import Annotated
from uuid import UUID

from fastapi import APIRouter, Depends, Header, HTTPException, Query
from sqlalchemy.exc import SQLAlchemyError
from sqlalchemy.orm import Session

from app.api.crm_routes import Actor
from app.api.whatsapp_configuration_dependencies import get_whatsapp_secret_cipher
from app.application.crm.customer_workspace import CustomerWorkspaceService
from app.application.crm.duplicates import DuplicateService
from app.application.crm.follow_up import FollowUpService
from app.application.crm.report import CommercialReportService
from app.application.crm.sales_metrics import SalesMetricsService
from app.application.crm.service import OpportunityService
from app.application.crm.suggestions import CommercialSuggestionService
from app.domain.crm.contracts import (
    CommercialContext,
    CrmConflict,
    CrmNotFound,
    FollowUpFilter,
    FollowUpList,
    HistoryRecord,
    OpportunityCreate,
    OpportunityList,
    OpportunityRecord,
    OpportunityUpdate,
    Stage,
    StageConfiguration,
)
from app.domain.crm.customer_contracts import (
    ActivityInput,
    ActivityList,
    CommercialReport,
    CommercialSuggestion,
    CustomerActionList,
    CustomerActivity,
    CustomerWorkspace,
)
from app.domain.crm.growth_contracts import (
    DuplicateList,
    MergeInput,
    MergePreview,
    MergeResult,
    SalesMetrics,
)
from app.infrastructure.database import get_session
from app.infrastructure.settings import get_settings
from app.security.authorization import AuthorizationError

router = APIRouter(
    prefix="/organizations/{organization_id}", tags=["crm-opportunities"]
)


def get_opportunity_service(
    session: Annotated[Session, Depends(get_session)],
) -> OpportunityService:
    return OpportunityService(
        session,
        get_whatsapp_secret_cipher(),
        get_settings().contact_identity_hmac_key,
    )


Service = Annotated[OpportunityService, Depends(get_opportunity_service)]


@router.get("/crm/follow-up", response_model=FollowUpList)
def follow_up(
    organization_id: UUID,
    actor: Actor,
    service: Service,
    due: FollowUpFilter = "all",
    assigned_user_id: UUID | None = None,
    stage_code: str | None = Query(default=None, max_length=40),
    page: int = Query(default=1, ge=1),
    page_size: int = Query(default=20, ge=1, le=100),
) -> FollowUpList:
    try:
        return FollowUpService(service.session, service.cipher).list(
            organization_id,
            actor,
            due=due,
            assigned_user_id=assigned_user_id,
            stage_code=stage_code,
            page=page,
            page_size=page_size,
        )
    except (ValueError, SQLAlchemyError) as exc:
        raise fail(exc) from exc


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


@router.get("/crm/customers/{contact_id}/workspace", response_model=CustomerWorkspace)
def customer_workspace(
    organization_id: UUID,
    contact_id: UUID,
    actor: Actor,
    service: Service,
    page: int = Query(default=1, ge=1),
    conversation_page: int = Query(default=1, ge=1),
) -> CustomerWorkspace:
    try:
        return CustomerWorkspaceService(service).workspace(
            organization_id, contact_id, actor, page, conversation_page
        )
    except (ValueError, SQLAlchemyError) as exc:
        raise fail(exc) from exc


@router.get("/crm/customers/{contact_id}/activities", response_model=ActivityList)
def customer_activities(
    organization_id: UUID,
    contact_id: UUID,
    actor: Actor,
    service: Service,
    page: int = Query(default=1, ge=1),
) -> ActivityList:
    try:
        return CustomerWorkspaceService(service).activities(
            organization_id, contact_id, actor, page
        )
    except (ValueError, SQLAlchemyError) as exc:
        raise fail(exc) from exc


@router.post(
    "/crm/customers/{contact_id}/activities",
    response_model=CustomerActivity,
    status_code=201,
)
def record_customer_activity(
    organization_id: UUID,
    contact_id: UUID,
    data: ActivityInput,
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
) -> CustomerActivity:
    try:
        return CustomerWorkspaceService(service).record_activity(
            organization_id, contact_id, actor, data, key
        )
    except (ValueError, SQLAlchemyError) as exc:
        raise fail(exc) from exc


@router.get("/crm/commercial-report", response_model=CommercialReport)
def commercial_report(
    organization_id: UUID,
    actor: Actor,
    service: Service,
    date_from: datetime | None = None,
    date_to: datetime | None = None,
    assigned_user_id: UUID | None = None,
) -> CommercialReport:
    try:
        return CommercialReportService(service).report(
            organization_id, actor, date_from, date_to, assigned_user_id
        )
    except (ValueError, SQLAlchemyError) as exc:
        raise fail(exc) from exc


@router.get(
    "/crm/customers/{contact_id}/suggestions/{conversation_id}",
    response_model=CommercialSuggestion,
)
def commercial_suggestion(
    organization_id: UUID,
    contact_id: UUID,
    conversation_id: UUID,
    actor: Actor,
    service: Service,
) -> CommercialSuggestion:
    try:
        return CommercialSuggestionService(service, get_settings()).suggest(
            organization_id, contact_id, conversation_id, actor
        )
    except (ValueError, SQLAlchemyError) as exc:
        raise fail(exc) from exc


@router.get(
    "/crm/customers/{contact_id}/action-history", response_model=CustomerActionList
)
def customer_action_history(
    organization_id: UUID,
    contact_id: UUID,
    actor: Actor,
    service: Service,
    page: int = Query(default=1, ge=1),
) -> CustomerActionList:
    try:
        return CustomerWorkspaceService(service).actions(
            organization_id, contact_id, actor, page
        )
    except (ValueError, SQLAlchemyError) as exc:
        raise fail(exc) from exc


@router.get("/crm/duplicates", response_model=DuplicateList)
def duplicate_candidates(
    organization_id: UUID,
    actor: Actor,
    service: Service,
    page: int = Query(default=1, ge=1),
) -> DuplicateList:
    try:
        return DuplicateService(service).candidates(organization_id, actor, page)
    except (ValueError, SQLAlchemyError) as exc:
        raise fail(exc) from exc


@router.get("/crm/merge-preview", response_model=MergePreview)
def merge_preview(
    organization_id: UUID,
    actor: Actor,
    service: Service,
    source_id: UUID,
    target_id: UUID,
) -> MergePreview:
    try:
        return DuplicateService(service).preview(
            organization_id, actor, source_id, target_id
        )
    except (ValueError, SQLAlchemyError) as exc:
        raise fail(exc) from exc


@router.post("/crm/customer-merges", response_model=MergeResult)
def merge_customers(
    organization_id: UUID, actor: Actor, service: Service, data: MergeInput
) -> MergeResult:
    try:
        return DuplicateService(service).merge(organization_id, actor, data)
    except (ValueError, SQLAlchemyError) as exc:
        raise fail(exc) from exc


@router.get("/crm/sales-metrics", response_model=SalesMetrics)
def sales_metrics(
    organization_id: UUID,
    actor: Actor,
    service: Service,
    date_from: datetime | None = None,
    date_to: datetime | None = None,
    assigned_user_id: UUID | None = None,
) -> SalesMetrics:
    try:
        return SalesMetricsService(service).report(
            organization_id, actor, date_from, date_to, assigned_user_id
        )
    except (ValueError, SQLAlchemyError) as exc:
        raise fail(exc) from exc


@router.get(
    "/crm/opportunities/{opportunity_id}/suggestions/{conversation_id}",
    response_model=CommercialSuggestion,
)
def opportunity_suggestion(
    organization_id: UUID,
    opportunity_id: UUID,
    conversation_id: UUID,
    actor: Actor,
    service: Service,
) -> CommercialSuggestion:
    try:
        return CommercialSuggestionService(service, get_settings()).for_opportunity(
            organization_id, opportunity_id, conversation_id, actor
        )
    except (ValueError, SQLAlchemyError) as exc:
        raise fail(exc) from exc
