"""Public, write-only contact registration for Luri. Disabled by default."""

import json
import os
import time
from collections import OrderedDict
from datetime import UTC, datetime
from threading import Lock
from typing import Annotated, Literal
from uuid import UUID, uuid4

from fastapi import APIRouter, Depends, FastAPI, HTTPException, Request
from fastapi.middleware.cors import CORSMiddleware
from pydantic import BaseModel, ConfigDict, Field
from sqlalchemy.exc import IntegrityError
from sqlalchemy.orm import Session

from app.application.contacts.identity import ContactIdentityHasher
from app.domain.contacts.contracts import ContactIdentityNormalizer
from app.infrastructure.database import get_session
from app.infrastructure.models.contact import ContactModel
from app.infrastructure.models.organization import OrganizationModel
from app.infrastructure.repositories.contact_repository import (
    SqlAlchemyContactRepository,
)
from app.infrastructure.settings import get_settings
from app.security.secret_cipher import EnvironmentSecretCipher, SecretCipher


class WindowLimiter:
    """Bounded single-process limit; configure edge limiting for replicas."""

    def __init__(self) -> None:
        self.lock = Lock()
        self.window = -1
        self.total = 0
        self.counts: OrderedDict[str, int] = OrderedDict()

    def allow(self, peer: str) -> bool:
        with self.lock:
            window = int(time.monotonic() // 60)
            if window != self.window:
                self.window, self.total = window, 0
                self.counts.clear()
            if self.total >= 120:
                return False
            self.total += 1
            count = self.counts.get(peer, 0) + 1
            self.counts[peer] = count
            return count <= 12


NOTICE_VERSION = "contact-registration-v1"


class Registration(BaseModel):
    model_config = ConfigDict(extra="forbid", str_strip_whitespace=True)
    name: str = Field(min_length=2, max_length=120)
    whatsapp: str = Field(pattern=r"^\+[1-9][0-9]{7,14}$")
    consent: Literal[True]
    notice_version: Literal["contact-registration-v1"]


def register_contact(
    session: Session,
    organization_id: UUID,
    body: Registration,
    hasher: ContactIdentityHasher,
    cipher: SecretCipher,
) -> None:
    """One commit; duplicate submissions never overwrite or reactivate a contact."""
    organization = session.get(OrganizationModel, organization_id)
    if organization is None or organization.status != "active":
        raise HTTPException(503, "Registration unavailable")
    identity = hasher.identify(organization_id, "whatsapp", body.whatsapp)
    repository = SqlAlchemyContactRepository(session)
    if repository.get_by_identity(
        organization_id, "whatsapp", identity.external_identifier_hash
    ):
        return
    contact = ContactModel(
        id=uuid4(),
        organization_id=organization_id,
        channel_type="whatsapp",
        external_identifier_hash=identity.external_identifier_hash,
        external_identifier_ciphertext=cipher.encrypt(identity.normalized_identifier),
        display_name_ciphertext=cipher.encrypt(body.name),
        registration_ciphertext=cipher.encrypt(
            json.dumps(
                {
                    "source": "website",
                    "identity_verified": False,
                    "consent": {
                        "purpose": "respond_to_service_enquiry",
                        "notice_version": NOTICE_VERSION,
                        "accepted_at": datetime.now(UTC).isoformat(),
                    },
                }
            )
        ),
        status="active",
        normalized_identifier_version=1,
    )
    try:
        repository.add(contact)
        session.commit()
    except IntegrityError:
        session.rollback()
        # A concurrent registration can win the same tenant/identity constraint.
        if repository.get_by_identity(
            organization_id, "whatsapp", identity.external_identifier_hash
        ):
            return
        raise
    except Exception:
        session.rollback()
        raise


def create_contacts_router(organization_id: UUID, origins: frozenset[str]) -> APIRouter:
    router = APIRouter(prefix="/public/contacts", tags=["public-contacts"])
    limiter = WindowLimiter()

    async def validate(request: Request) -> Registration:
        if request.headers.get("origin") not in origins:
            raise HTTPException(403, "Origin not allowed")
        if not limiter.allow(request.client.host if request.client else "unknown"):
            raise HTTPException(429, "Too many requests", headers={"Retry-After": "60"})
        if request.headers.get("content-type", "").split(";")[0] != "application/json":
            raise HTTPException(415, "JSON required")
        raw = bytearray()
        async for chunk in request.stream():
            raw.extend(chunk)
            if len(raw) > 4096:
                raise HTTPException(413, "Request too large")
        try:
            return Registration.model_validate_json(bytes(raw))
        except ValueError as exc:
            raise HTTPException(422, "Invalid registration") from exc

    @router.post("", status_code=200)
    def register(
        body: Annotated[Registration, Depends(validate)],
        session: Annotated[Session, Depends(get_session)],
    ) -> dict[str, bool]:
        settings = get_settings()
        try:
            register_contact(
                session,
                organization_id,
                body,
                ContactIdentityHasher(
                    settings.contact_identity_hmac_key, ContactIdentityNormalizer()
                ),
                EnvironmentSecretCipher.from_settings(settings),
            )
        except HTTPException:
            raise
        except Exception as exc:
            # Never return database errors or personal information to visitors.
            raise HTTPException(503, "Registration unavailable") from exc
        return {"accepted": True}

    return router


def install_public_contacts(app: FastAPI) -> None:
    if os.environ.get("LURI_PUBLIC_CONTACTS_ENABLED") != "true":
        return
    organization_id = UUID(os.environ["LURI_PUBLIC_CONTACTS_ORGANIZATION_ID"])
    origins = frozenset(
        value.strip()
        for value in os.environ["LURI_PUBLIC_CONTACTS_ORIGINS"].split(",")
        if value.strip()
    )
    if not origins or "*" in origins:
        raise ValueError("Explicit contact origins are required")
    # Isolate CORS to this public sub-application; do not change portal policies.
    public = FastAPI(docs_url=None, redoc_url=None, openapi_url=None)
    public.include_router(create_contacts_router(organization_id, origins))
    public.add_middleware(
        CORSMiddleware,
        allow_origins=list(origins),
        allow_methods=["POST"],
        allow_headers=["Content-Type"],
    )
    app.mount("/website", public)
