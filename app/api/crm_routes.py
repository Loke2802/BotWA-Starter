from collections.abc import Generator
from typing import Annotated, Literal
from uuid import UUID

from fastapi import APIRouter, Depends, HTTPException, Query

from app.api.dependencies import require_authenticated_user
from app.api.whatsapp_configuration_dependencies import get_whatsapp_secret_cipher
from app.application.contacts.crm import CrmConflict, CrmNotFound, CrmService
from app.application.contacts.identity import ContactIdentityHasher
from app.domain.contacts.contracts import ContactIdentityNormalizer
from app.domain.contacts.crm_contracts import (
    CrmAssignee,
    CrmSummary,
    CustomerCreate,
    CustomerDetail,
    CustomerList,
    CustomerUpdate,
)
from app.domain.user.contracts import User
from app.infrastructure.database import get_session
from app.infrastructure.settings import get_settings
from app.security.authorization import AuthorizationError

router = APIRouter(prefix="/organizations/{organization_id}/crm", tags=["crm"])


def get_crm_service() -> Generator[CrmService]:
    sessions = get_session()
    session = next(sessions)
    try:
        yield CrmService(
            session,
            get_whatsapp_secret_cipher(),
            ContactIdentityHasher(
                get_settings().contact_identity_hmac_key, ContactIdentityNormalizer()
            ),
        )
    finally:
        sessions.close()


Service = Annotated[CrmService, Depends(get_crm_service)]
Actor = Annotated[User, Depends(require_authenticated_user)]


def fail(exc: ValueError) -> HTTPException:
    if isinstance(exc, AuthorizationError):
        return HTTPException(403, "No tienes permiso para realizar esta acción.")
    if isinstance(exc, CrmNotFound):
        return HTTPException(404, "No encontramos este contacto en tu empresa.")
    if isinstance(exc, CrmConflict):
        return HTTPException(409, str(exc))
    return HTTPException(400, "Revisa los datos y el responsable seleccionado.")


@router.get("/summary", response_model=CrmSummary)
def summary(organization_id: UUID, actor: Actor, service: Service) -> CrmSummary:
    try:
        return service.summary(organization_id, actor)
    except ValueError as exc:
        raise fail(exc) from exc


@router.get("/assignees", response_model=list[CrmAssignee])
def assignees(
    organization_id: UUID, actor: Actor, service: Service
) -> list[CrmAssignee]:
    try:
        return service.assignees(organization_id, actor)
    except ValueError as exc:
        raise fail(exc) from exc


@router.get("/customers", response_model=CustomerList)
def customers(
    organization_id: UUID,
    actor: Actor,
    service: Service,
    classification: Literal["lead", "customer", "inactive"] | None = None,
    status: Literal["active", "archived"] = "active",
    due: bool = False,
    identifier: str | None = Query(default=None, max_length=32),
    page: int = Query(default=1, ge=1),
    page_size: int = Query(default=20, ge=1, le=100),
) -> CustomerList:
    try:
        return service.list_customers(
            organization_id,
            actor,
            classification=classification,
            status=status,
            due=due,
            identifier=identifier,
            page=page,
            page_size=page_size,
        )
    except ValueError as exc:
        raise fail(exc) from exc


@router.post("/customers", response_model=CustomerDetail, status_code=201)
def create(
    organization_id: UUID, data: CustomerCreate, actor: Actor, service: Service
) -> CustomerDetail:
    try:
        return service.create(organization_id, actor, data)
    except ValueError as exc:
        raise fail(exc) from exc


@router.get("/customers/{contact_id}", response_model=CustomerDetail)
def detail(
    organization_id: UUID, contact_id: UUID, actor: Actor, service: Service
) -> CustomerDetail:
    try:
        return service.detail(organization_id, contact_id, actor)
    except ValueError as exc:
        raise fail(exc) from exc


@router.put("/customers/{contact_id}", response_model=CustomerDetail)
def update(
    organization_id: UUID,
    contact_id: UUID,
    data: CustomerUpdate,
    actor: Actor,
    service: Service,
) -> CustomerDetail:
    try:
        return service.update(organization_id, contact_id, actor, data)
    except ValueError as exc:
        raise fail(exc) from exc
