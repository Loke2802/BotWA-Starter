"""Real PostgreSQL locking and tenant constraints for the intranet CRM."""

import base64
import os
from concurrent.futures import ThreadPoolExecutor
from threading import Barrier
from uuid import uuid4

import pytest
from app.application.contacts.crm import CrmConflict, CrmService
from app.application.contacts.identity import ContactIdentityHasher
from app.domain.contacts.contracts import ContactIdentityNormalizer
from app.domain.contacts.crm_contracts import CustomerCreate, CustomerUpdate
from app.domain.user.contracts import User
from app.infrastructure.models.organization import OrganizationModel
from app.infrastructure.models.user import UserModel
from app.security.secret_cipher import EnvironmentSecretCipher
from sqlalchemy import create_engine, text
from sqlalchemy.orm import Session

DATABASE_URL = os.getenv("BOTWA_CRM_POSTGRES_URL")
pytestmark = pytest.mark.skipif(
    not DATABASE_URL, reason="Explicit CRM PostgreSQL test URL required"
)


def service(session: Session) -> CrmService:
    return CrmService(
        session,
        EnvironmentSecretCipher(base64.urlsafe_b64encode(b"c" * 32).decode()),
        ContactIdentityHasher(
            "crm-postgresql-test-key-at-least-thirty-two-characters",
            ContactIdentityNormalizer(),
        ),
    )


def test_postgresql_concurrent_edits_do_not_overwrite() -> None:
    assert DATABASE_URL is not None
    engine = create_engine(DATABASE_URL)
    org = uuid4()
    actor = User(
        id=uuid4(),
        organization_id=org,
        email=f"{org}@example.test",
        role="organization_admin",
    )
    try:
        with Session(engine) as session:
            session.add(
                OrganizationModel(
                    id=org,
                    name="CRM concurrency test",
                    slug=f"crm-{org}",
                    status="active",
                )
            )
            session.flush()
            session.add(
                UserModel(
                    id=actor.id,
                    organization_id=org,
                    email=actor.email,
                    password_hash="test-only",
                    role=actor.role,
                    status="active",
                )
            )
            session.commit()
            created = service(session).create(
                org,
                actor,
                CustomerCreate(display_name="Prueba ficticia", whatsapp="+12025550149"),
            )
        barrier = Barrier(2)

        def edit(name: str) -> str:
            with Session(engine) as session:
                barrier.wait(timeout=10)
                try:
                    service(session).update(
                        org,
                        created.id,
                        actor,
                        CustomerUpdate(display_name=name, version=1),
                    )
                    return "saved"
                except CrmConflict:
                    return "conflict"

        with ThreadPoolExecutor(max_workers=2) as pool:
            results = list(pool.map(edit, ["Primer cambio", "Segundo cambio"]))
        assert sorted(results) == ["conflict", "saved"]
        with Session(engine) as session:
            assert service(session).detail(org, created.id, actor).version == 2
    finally:
        with engine.begin() as connection:
            for table in ("audit_event", "customer_profile", "contact", "app_user"):
                connection.execute(
                    text(f"DELETE FROM {table} WHERE organization_id = :org"),
                    {"org": org},
                )
            connection.execute(
                text("DELETE FROM organization WHERE id = :org"), {"org": org}
            )
        engine.dispose()
