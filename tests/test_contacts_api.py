# ruff: noqa: E501

import base64
from collections.abc import Generator
from datetime import UTC, datetime, timedelta
from typing import cast
from uuid import UUID, uuid4

import pytest
from app.api.contacts_dependencies import get_contact_administration_service
from app.api.conversation_management_dependencies import (
    get_conversation_management_service,
)
from app.api.dependencies import require_authenticated_user
from app.application.contacts.administration import ContactAdministrationService
from app.application.contacts.identity import ContactIdentityHasher
from app.application.conversation_management.service import (
    ConversationManagementService,
)
from app.domain.access.contracts import Role
from app.domain.contacts.contracts import ContactIdentityNormalizer
from app.domain.user.contracts import User
from app.infrastructure.database import Base
from app.infrastructure.models.bot import BotModel
from app.infrastructure.models.contact import ContactModel
from app.infrastructure.models.conversation import ConversationModel
from app.infrastructure.models.organization import OrganizationModel
from app.infrastructure.repositories.audit_repository import SqlAlchemyAuditRepository
from app.infrastructure.repositories.bot_repository import BotRepository
from app.infrastructure.repositories.contact_repository import (
    SqlAlchemyContactRepository,
)
from app.infrastructure.repositories.conversation_management_repository import (
    SqlAlchemyConversationManagementRepository,
    SqlAlchemyConversationMessageManagementRepository,
)
from app.main import create_app
from app.security.secret_cipher import EnvironmentSecretCipher
from fastapi import FastAPI
from fastapi.testclient import TestClient
from sqlalchemy import create_engine
from sqlalchemy.orm import Session, sessionmaker
from sqlalchemy.pool import StaticPool

NOW = datetime(2026, 8, 6, 12, tzinfo=UTC)
HMAC_KEY = "contacts-api-test-hmac-key-with-at-least-thirty-two-characters"


def _cipher() -> EnvironmentSecretCipher:
    return EnvironmentSecretCipher(base64.urlsafe_b64encode(b"k" * 32).decode())


def _actor(organization_id: UUID, role: str) -> User:
    return User(
        id=uuid4(),
        organization_id=organization_id,
        email=f"{role}-{uuid4()}@example.test",
        role=cast(Role, role),
    )


@pytest.fixture
def runtime() -> Generator[tuple[TestClient, Session, dict[str, object]]]:
    engine = create_engine(
        "sqlite:///:memory:",
        connect_args={"check_same_thread": False},
        poolclass=StaticPool,
    )
    Base.metadata.create_all(engine)
    session = sessionmaker(bind=engine)()
    cipher = _cipher()
    organization_id, other_organization_id = uuid4(), uuid4()
    bot_id, other_bot_id = uuid4(), uuid4()
    session.add_all(
        (
            OrganizationModel(
                id=organization_id, name="Org", slug="contacts-org", status="active"
            ),
            OrganizationModel(
                id=other_organization_id,
                name="Other",
                slug="contacts-other",
                status="active",
            ),
            BotModel(
                id=bot_id,
                organization_id=organization_id,
                name="Bot",
                slug="contacts-bot",
                status="active",
            ),
            BotModel(
                id=other_bot_id,
                organization_id=organization_id,
                name="Bot Two",
                slug="contacts-bot-two",
                status="active",
            ),
        )
    )
    hasher = ContactIdentityHasher(HMAC_KEY, ContactIdentityNormalizer())

    def contact(
        organization: UUID,
        identifier: str,
        *,
        status: str = "active",
        created_at: datetime = NOW,
    ) -> ContactModel:
        identity = hasher.identify(organization, "whatsapp", identifier)
        return ContactModel(
            id=uuid4(),
            organization_id=organization,
            channel_type="whatsapp",
            external_identifier_hash=identity.external_identifier_hash,
            external_identifier_ciphertext=cipher.encrypt(
                identity.normalized_identifier
            ),
            display_name_ciphertext=cipher.encrypt("Visible name"),
            notes_ciphertext=cipher.encrypt("Private note"),
            status=status,
            created_at=created_at,
            updated_at=created_at,
        )

    primary = contact(organization_id, "51999999999")
    archived = contact(
        organization_id,
        "51888888888",
        status="archived",
        created_at=NOW + timedelta(seconds=1),
    )
    other = contact(other_organization_id, "51999999999")
    session.add_all((primary, archived, other))
    session.add_all(
        (
            ConversationModel(
                id=uuid4(),
                company_id=str(organization_id),
                customer_id="x",
                organization_id=organization_id,
                bot_id=bot_id,
                external_customer_id="x",
                contact_id=primary.id,
                channel="whatsapp",
                management_status="open",
                status="new",
                started_at=NOW,
            ),
            ConversationModel(
                id=uuid4(),
                company_id=str(organization_id),
                customer_id="y",
                organization_id=organization_id,
                bot_id=other_bot_id,
                external_customer_id="y",
                contact_id=primary.id,
                channel="whatsapp",
                management_status="open",
                status="new",
                started_at=NOW + timedelta(seconds=1),
            ),
            ConversationModel(
                id=uuid4(),
                company_id=str(other_organization_id),
                customer_id="z",
                organization_id=other_organization_id,
                bot_id=uuid4(),
                external_customer_id="z",
                contact_id=other.id,
                channel="whatsapp",
                management_status="open",
                status="new",
                started_at=NOW,
            ),
        )
    )
    session.commit()
    contact_service = ContactAdministrationService(
        SqlAlchemyContactRepository(session), hasher, cipher, session
    )
    audit_writer = SqlAlchemyAuditRepository(session)
    conversation_service = ConversationManagementService(
        SqlAlchemyConversationManagementRepository(session),
        SqlAlchemyConversationMessageManagementRepository(session, audit_writer),
        BotRepository(session),
        cipher,
        session,
        audit_writer,
    )
    actors = {
        "viewer": _actor(organization_id, "viewer"),
        "operator": _actor(organization_id, "operator"),
        "admin": _actor(organization_id, "organization_admin"),
        "platform": _actor(organization_id, "platform_admin"),
    }
    app = create_app()
    app.dependency_overrides[get_contact_administration_service] = (
        lambda: contact_service
    )
    app.dependency_overrides[get_conversation_management_service] = (
        lambda: conversation_service
    )
    app.dependency_overrides[require_authenticated_user] = lambda: actors["admin"]
    data: dict[str, object] = {
        "organization_id": organization_id,
        "other_organization_id": other_organization_id,
        "bot_id": bot_id,
        "primary": primary,
        "archived": archived,
        "other": other,
        "actors": actors,
    }
    try:
        with TestClient(app) as client:
            yield client, session, data
    finally:
        session.close()
        app.dependency_overrides.clear()


def _as(client: TestClient, data: dict[str, object], role: str) -> None:
    actors = cast(dict[str, User], data["actors"])
    cast(FastAPI, client.app).dependency_overrides[require_authenticated_user] = (
        lambda: actors[role]
    )


def test_viewer_gets_non_sensitive_contact_view(
    runtime: tuple[TestClient, Session, dict[str, object]],
) -> None:
    client, _, data = runtime
    _as(client, data, "viewer")
    organization_id, primary = cast(UUID, data["organization_id"]), cast(
        ContactModel, data["primary"]
    )

    listed = client.get(f"/organizations/{organization_id}/contacts")
    detail = client.get(f"/organizations/{organization_id}/contacts/{primary.id}")

    assert listed.status_code == detail.status_code == 200
    assert listed.json()["total"] == 1
    assert detail.json()["display_name"] == "Visible name"
    assert detail.json()["external_identifier"] is None
    assert detail.json()["notes"] is None
    assert "ciphertext" not in detail.text and "hash" not in detail.text


def test_operator_can_update_without_reading_sensitive_values(
    runtime: tuple[TestClient, Session, dict[str, object]],
) -> None:
    client, session, data = runtime
    _as(client, data, "operator")
    organization_id, primary = cast(UUID, data["organization_id"]), cast(
        ContactModel, data["primary"]
    )

    update = client.patch(
        f"/organizations/{organization_id}/contacts/{primary.id}",
        json={"display_name": "Updated name", "notes": "Updated private"},
    )
    detail = client.get(f"/organizations/{organization_id}/contacts/{primary.id}")
    forbidden = client.patch(
        f"/organizations/{organization_id}/contacts/{primary.id}",
        json={"status": "archived"},
    )

    session.refresh(primary)
    assert update.status_code == 200
    assert detail.json()["notes"] is None
    assert primary.notes_ciphertext != "Updated private"
    assert forbidden.status_code == 422


def test_admin_filters_exact_search_and_archive_lifecycle(
    runtime: tuple[TestClient, Session, dict[str, object]],
) -> None:
    client, session, data = runtime
    _as(client, data, "admin")
    organization_id = cast(UUID, data["organization_id"])
    primary, archived = cast(ContactModel, data["primary"]), cast(
        ContactModel, data["archived"]
    )

    exact = client.get(
        f"/organizations/{organization_id}/contacts",
        params={"channel_type": "whatsapp", "identifier": "51999999999"},
    )
    archived_list = client.get(
        f"/organizations/{organization_id}/contacts", params={"status": "archived"}
    )
    archive = client.post(
        f"/organizations/{organization_id}/contacts/{primary.id}/archive"
    )
    archive_again = client.post(
        f"/organizations/{organization_id}/contacts/{primary.id}/archive"
    )
    reactivate = client.post(
        f"/organizations/{organization_id}/contacts/{primary.id}/reactivate"
    )

    session.refresh(primary)
    assert exact.status_code == 200 and exact.json()["total"] == 1
    assert archived_list.status_code == 200 and archived_list.json()["items"][0][
        "id"
    ] == str(archived.id)
    assert (
        archive.status_code
        == archive_again.status_code
        == reactivate.status_code
        == 200
    )
    assert primary.status == "active"


def test_sensitive_search_and_cross_tenant_are_protected(
    runtime: tuple[TestClient, Session, dict[str, object]],
) -> None:
    client, _, data = runtime
    organization_id, other_organization_id = cast(UUID, data["organization_id"]), cast(
        UUID, data["other_organization_id"]
    )
    other = cast(ContactModel, data["other"])
    _as(client, data, "viewer")
    search = client.get(
        f"/organizations/{organization_id}/contacts",
        params={"channel_type": "whatsapp", "identifier": "51999999999"},
    )
    _as(client, data, "admin")
    cross_read = client.get(f"/organizations/{organization_id}/contacts/{other.id}")
    cross_update = client.patch(
        f"/organizations/{organization_id}/contacts/{other.id}",
        json={"display_name": "no"},
    )
    cross_archive = client.post(
        f"/organizations/{organization_id}/contacts/{other.id}/archive"
    )
    _as(client, data, "platform")
    platform_read = client.get(
        f"/organizations/{other_organization_id}/contacts/{other.id}"
    )

    assert search.status_code == 403
    assert (
        cross_read.status_code
        == cross_update.status_code
        == cross_archive.status_code
        == 404
    )
    assert (
        platform_read.status_code == 200
        and platform_read.json()["external_identifier"] == "51999999999"
    )


def test_bot_filter_pagination_and_associated_conversations(
    runtime: tuple[TestClient, Session, dict[str, object]],
) -> None:
    client, _, data = runtime
    _as(client, data, "admin")
    organization_id, bot_id = cast(UUID, data["organization_id"]), cast(
        UUID, data["bot_id"]
    )
    primary = cast(ContactModel, data["primary"])

    filtered = client.get(
        f"/organizations/{organization_id}/contacts",
        params={"bot_id": str(bot_id), "page_size": 1},
    )
    conversations = client.get(
        f"/organizations/{organization_id}/contacts/{primary.id}/conversations",
        params={"page_size": 1},
    )

    assert filtered.status_code == 200 and filtered.json()["total"] == 1
    assert conversations.status_code == 200
    assert conversations.json()["total"] == 2
    assert len(conversations.json()["items"]) == 1
