import base64
from collections.abc import Generator
from uuid import uuid4

import pytest
from app.api.crm_routes import get_crm_service
from app.api.dependencies import require_authenticated_user
from app.application.contacts.crm import CrmService
from app.application.contacts.identity import ContactIdentityHasher
from app.domain.contacts.contracts import ContactIdentityNormalizer
from app.domain.user.contracts import User
from app.infrastructure.database import Base
from app.infrastructure.models.contact import ContactModel
from app.infrastructure.models.customer_profile import CustomerProfileModel
from app.infrastructure.models.organization import OrganizationModel
from app.infrastructure.models.user import UserModel
from app.main import create_app
from app.security.secret_cipher import EnvironmentSecretCipher
from fastapi.testclient import TestClient
from sqlalchemy import create_engine, event, select
from sqlalchemy.exc import IntegrityError
from sqlalchemy.orm import Session
from sqlalchemy.pool import StaticPool


@pytest.fixture
def crm() -> Generator[tuple[TestClient, Session, User, User, CrmService]]:
    engine = create_engine(
        "sqlite://", connect_args={"check_same_thread": False}, poolclass=StaticPool
    )

    @event.listens_for(engine, "connect")
    def foreign_keys(connection, _):  # type: ignore[no-untyped-def]
        connection.execute("PRAGMA foreign_keys=ON")

    Base.metadata.create_all(engine)
    with Session(engine) as session:
        org, other = uuid4(), uuid4()
        session.add_all(
            [
                OrganizationModel(
                    id=org, name="Kalivur test", slug="crm-test", status="active"
                ),
                OrganizationModel(
                    id=other, name="Other", slug="crm-other", status="active"
                ),
            ]
        )
        session.flush()
        actor = User(
            id=uuid4(),
            organization_id=org,
            email="crm@example.test",
            role="organization_admin",
        )
        other_actor = User(
            id=uuid4(),
            organization_id=other,
            email="other@example.test",
            role="organization_admin",
        )
        session.add_all(
            [
                UserModel(
                    id=u.id,
                    organization_id=u.organization_id,
                    email=u.email,
                    password_hash="not-a-login",
                    role=u.role,
                    first_name="Prueba",
                    status="active",
                )
                for u in [actor, other_actor]
            ]
        )
        session.commit()
        cipher = EnvironmentSecretCipher(base64.urlsafe_b64encode(b"c" * 32).decode())
        service = CrmService(
            session,
            cipher,
            ContactIdentityHasher(
                "crm-test-key-that-is-at-least-thirty-two-characters",
                ContactIdentityNormalizer(),
            ),
        )
        app = create_app()
        app.dependency_overrides[get_crm_service] = lambda: service
        app.dependency_overrides[require_authenticated_user] = lambda: actor
        with TestClient(app) as client:
            yield client, session, actor, other_actor, service


def payload(**changes: object) -> dict[str, object]:
    return {
        "display_name": "Cliente ficticio",
        "whatsapp": "+12025550147",
        "notes": "Consulta privada",
        "service_interest": "luri",
        **changes,
    }


def test_create_persists_encrypted_and_deduplicates(crm):  # type: ignore[no-untyped-def]
    client, session, actor, _, service = crm
    url = f"/organizations/{actor.organization_id}/crm/customers"
    response = client.post(url, json=payload())
    assert response.status_code == 201, response.text
    record = response.json()
    assert record["version"] == 1
    session.expire_all()
    contact = session.scalar(select(ContactModel))
    assert contact.display_name_ciphertext != "Cliente ficticio"
    assert "12025550147" not in contact.external_identifier_ciphertext
    assert service.cipher.decrypt(contact.notes_ciphertext) == "Consulta privada"
    assert (
        client.get(url + "/" + record["id"]).json()["display_name"]
        == "Cliente ficticio"
    )
    assert client.post(url, json=payload(display_name="Duplicate")).status_code == 409
    assert client.get(url).json()["total"] == 1


def test_update_conflict_and_follow_up_filters(crm):  # type: ignore[no-untyped-def]
    client, session, actor, _, _ = crm
    url = f"/organizations/{actor.organization_id}/crm/customers"
    created = client.post(url, json=payload()).json()
    update = {
        "display_name": "Cliente atendido",
        "version": 1,
        "classification": "customer",
        "service_interest": "site",
        "next_follow_up_at": "2020-01-01T10:00:00-05:00",
        "assigned_user_id": str(actor.id),
        "notes": "Nuevo acuerdo",
    }
    assert client.put(url + "/" + created["id"], json=update).status_code == 200
    assert client.put(url + "/" + created["id"], json=update).status_code == 409
    session.expire_all()
    assert client.get(url + "?classification=customer&due=true").json()["total"] == 1
    assert client.get(url + "?classification=lead").json()["total"] == 0
    summary = client.get(f"/organizations/{actor.organization_id}/crm/summary").json()
    assert summary["customers"] == 1 and summary["follow_ups_due"] == 1


def test_tenant_and_responsible_isolation(crm):  # type: ignore[no-untyped-def]
    client, session, actor, other, _ = crm
    url = f"/organizations/{actor.organization_id}/crm/customers"
    assert (
        client.post(url, json=payload(assigned_user_id=str(other.id))).status_code
        == 400
    )
    assert (
        client.get(f"/organizations/{other.organization_id}/crm/customers").status_code
        == 403
    )
    created = client.post(url, json=payload()).json()
    client.app.dependency_overrides[require_authenticated_user] = lambda: other
    assert (
        client.get(
            f"/organizations/{other.organization_id}/crm/customers/{created['id']}"
        ).status_code
        == 404
    )
    assert (
        client.get(f"/organizations/{other.organization_id}/crm/customers").json()[
            "total"
        ]
        == 0
    )
    assert (
        client.post(
            f"/organizations/{other.organization_id}/crm/customers", json=payload()
        ).status_code
        == 201
    )


def test_viewer_cannot_write_or_read_sensitive(crm):  # type: ignore[no-untyped-def]
    client, _, actor, _, _ = crm
    url = f"/organizations/{actor.organization_id}/crm/customers"
    created = client.post(url, json=payload()).json()
    viewer = actor.model_copy(update={"role": "viewer"})
    client.app.dependency_overrides[require_authenticated_user] = lambda: viewer
    detail = client.get(url + "/" + created["id"]).json()
    assert detail["notes"] is None and detail["external_identifier"] is None
    assert detail["can_edit"] is False
    assert client.post(url, json=payload()).status_code == 403
    assert (
        client.put(
            url + "/" + created["id"], json={"display_name": "Changed", "version": 1}
        ).status_code
        == 403
    )
    assert client.get(url + "?identifier=12025550147").status_code == 403


def test_existing_contacts_are_visible_without_profile(crm):  # type: ignore[no-untyped-def]
    client, session, actor, _, service = crm
    identity = service.hasher.identify(actor.organization_id, "whatsapp", "12025550148")
    contact = ContactModel(
        organization_id=actor.organization_id,
        channel_type="whatsapp",
        external_identifier_hash=identity.external_identifier_hash,
        external_identifier_ciphertext=service.cipher.encrypt(
            identity.normalized_identifier
        ),
        display_name_ciphertext=service.cipher.encrypt("Anterior"),
    )
    session.add(contact)
    session.commit()
    url = f"/organizations/{actor.organization_id}/crm/customers"
    listed = client.get(url).json()["items"][0]
    assert listed["version"] == 0 and listed["classification"] == "lead"
    assert (
        client.put(
            url + "/" + listed["id"],
            json={"display_name": "Anterior actualizado", "version": 0},
        ).status_code
        == 200
    )


def test_database_rejects_cross_tenant_profile(crm):  # type: ignore[no-untyped-def]
    client, session, actor, other, _ = crm
    created = client.post(
        f"/organizations/{actor.organization_id}/crm/customers", json=payload()
    ).json()
    from uuid import UUID

    profile = session.get(CustomerProfileModel, UUID(created["id"]))
    profile.organization_id = other.organization_id
    with pytest.raises(IntegrityError):
        session.commit()
    session.rollback()


@pytest.mark.parametrize(
    "change",
    [
        {"whatsapp": "123"},
        {"display_name": " "},
        {"classification": "invalid"},
        {"next_follow_up_at": "2026-09-20T14:00:00"},
        {"organization_id": str(uuid4())},
    ],
)
def test_invalid_input_is_rejected(crm, change):  # type: ignore[no-untyped-def]
    client, _, actor, _, _ = crm
    assert (
        client.post(
            f"/organizations/{actor.organization_id}/crm/customers",
            json=payload(**change),
        ).status_code
        == 422
    )
