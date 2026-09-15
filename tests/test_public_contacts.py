from collections.abc import Generator
from typing import cast
from uuid import uuid4

import pytest
from app.api import public_contacts_routes as channel
from app.application.contacts.identity import ContactIdentityHasher
from app.domain.contacts.contracts import ContactIdentityNormalizer
from app.infrastructure.database import Base, get_session
from app.infrastructure.models.contact import ContactModel
from app.infrastructure.models.organization import OrganizationModel
from app.infrastructure.settings import Settings
from app.security.secret_cipher import EnvironmentSecretCipher
from cryptography.fernet import Fernet
from fastapi import FastAPI
from fastapi.testclient import TestClient
from httpx import Response
from sqlalchemy import create_engine, select
from sqlalchemy.orm import Session
from sqlalchemy.pool import StaticPool

DatabaseFixture = tuple[Session, OrganizationModel, TestClient, EnvironmentSecretCipher]


@pytest.fixture
def setup_db(monkeypatch: pytest.MonkeyPatch) -> Generator[DatabaseFixture]:
    engine = create_engine(
        "sqlite://", connect_args={"check_same_thread": False}, poolclass=StaticPool
    )
    Base.metadata.create_all(
        engine,
        tables=[
            Base.metadata.tables[n] for n in ("organization", "app_user", "contact")
        ],
    )
    session = Session(engine)
    org = OrganizationModel(id=uuid4(), name="Test", slug="test", status="active")
    session.add(org)
    session.commit()
    settings = Settings(
        contact_identity_hmac_key="test-key-only",
        whatsapp_secret_encryption_key=Fernet.generate_key().decode(),
        whatsapp_secret_previous_encryption_keys="",
    )
    monkeypatch.setattr(channel, "get_settings", lambda: settings)
    app = FastAPI()
    app.include_router(
        channel.create_contacts_router(org.id, frozenset({"http://localhost:3002"}))
    )
    app.dependency_overrides[get_session] = lambda: session
    with TestClient(app) as client:
        yield session, org, client, EnvironmentSecretCipher.from_settings(settings)
    session.close()
    engine.dispose()


def post(client: TestClient, **changes: object) -> Response:
    body: dict[str, object] = dict(
        name="Cliente de prueba",
        whatsapp="+51900000001",
        consent=True,
        notice_version="contact-registration-v1",
    )
    body.update(changes)
    return cast(
        Response,
        client.post(
            "/public/contacts", json=body, headers={"Origin": "http://localhost:3002"}
        ),
    )


def test_persists_encrypted_contact_and_deduplicates(setup_db: DatabaseFixture) -> None:
    session, org, client, cipher = setup_db
    assert post(client).json() == {"accepted": True}
    session.expire_all()
    contact = session.scalars(select(ContactModel)).one()
    assert contact.display_name_ciphertext is not None
    assert contact.notes_ciphertext is not None
    assert contact.organization_id == org.id
    assert cipher.decrypt(contact.display_name_ciphertext) == "Cliente de prueba"
    assert cipher.decrypt(contact.external_identifier_ciphertext) == "51900000001"
    assert "Cliente" not in contact.display_name_ciphertext
    assert "contact-registration-v1" in cipher.decrypt(contact.notes_ciphertext)
    contact.status = "archived"
    session.commit()
    assert post(client, name="Intento de reemplazo").status_code == 200
    session.expire_all()
    assert len(session.scalars(select(ContactModel)).all()) == 1
    assert cipher.decrypt(contact.display_name_ciphertext) == "Cliente de prueba"
    assert contact.status == "archived"


@pytest.mark.parametrize(
    "change",
    [
        {"consent": False},
        {"organization_id": str(uuid4())},
        {"whatsapp": "123"},
        {"notice_version": "unknown"},
        {"name": " "},
    ],
)
def test_invalid_requests_do_not_write(
    setup_db: DatabaseFixture, change: dict[str, object]
) -> None:
    session, _, client, _ = setup_db
    assert post(client, **change).status_code == 422
    assert session.scalars(select(ContactModel)).first() is None


def test_inactive_tenant_and_origin_rejected(setup_db: DatabaseFixture) -> None:
    session, org, client, _ = setup_db
    assert client.post("/public/contacts", json={}).status_code == 403
    org.status = "inactive"
    session.commit()
    assert post(client).status_code == 503
    assert session.scalars(select(ContactModel)).first() is None


def test_failed_commit_does_not_acknowledge_or_leave_contact(
    setup_db: DatabaseFixture, monkeypatch: pytest.MonkeyPatch
) -> None:
    session, _, client, _ = setup_db

    def fail() -> None:
        raise RuntimeError("database unavailable")

    monkeypatch.setattr(session, "commit", fail)
    assert post(client).status_code == 503
    assert session.scalars(select(ContactModel)).first() is None


def test_same_phone_is_scoped_to_other_tenant(setup_db: DatabaseFixture) -> None:
    session, _, client, cipher = setup_db
    assert post(client).status_code == 200
    other = OrganizationModel(id=uuid4(), name="Other", slug="other", status="active")
    session.add(other)
    session.commit()
    channel.register_contact(
        session,
        other.id,
        channel.Registration(
            name="Other person",
            whatsapp="+51900000001",
            consent=True,
            notice_version="contact-registration-v1",
        ),
        ContactIdentityHasher("test-key-only", ContactIdentityNormalizer()),
        cipher,
    )
    contacts = session.scalars(select(ContactModel)).all()
    assert len(contacts) == 2
    assert contacts[0].external_identifier_hash != contacts[1].external_identifier_hash
