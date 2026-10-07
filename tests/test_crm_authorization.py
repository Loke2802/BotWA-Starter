"""CRM access through real JWT authentication and fresh persisted account state."""

from collections.abc import Generator
from dataclasses import dataclass
from datetime import UTC, datetime, timedelta
from pathlib import Path
from typing import Any
from uuid import UUID, uuid4

import jwt
import pytest
from app.api import crm_opportunity_routes, crm_routes
from app.api.dependencies import get_access_token_service
from app.application.contacts.crm import CrmService
from app.application.contacts.identity import ContactIdentityHasher
from app.application.crm.customer_workspace import CustomerWorkspaceService
from app.domain.contacts.contracts import ContactIdentityNormalizer
from app.domain.contacts.crm_contracts import CustomerCreate
from app.domain.crm.contracts import OpportunityCreate
from app.domain.crm.customer_contracts import ActivityInput
from app.domain.user.contracts import User
from app.infrastructure import database
from app.infrastructure.database import Base
from app.infrastructure.models.audit import AuditEventModel
from app.infrastructure.models.bot import BotModel
from app.infrastructure.models.conversation import ConversationModel
from app.infrastructure.models.crm_contact_merge import ContactMergeModel
from app.infrastructure.models.crm_customer_activity import CrmCustomerActivityModel
from app.infrastructure.models.crm_opportunity import (
    OpportunityActivityModel,
    OpportunityConversationModel,
    OpportunityHistoryModel,
    OpportunityModel,
)
from app.infrastructure.models.organization import OrganizationModel
from app.infrastructure.models.user import UserModel
from app.infrastructure.settings import get_settings
from app.main import create_app
from app.security.secret_cipher import SecretCipher
from fastapi.testclient import TestClient
from sqlalchemy import Engine, create_engine, event, func, select
from sqlalchemy.orm import Session, sessionmaker

from tests.crm_opportunity_support import opportunity_service, payload, seed


class ObservedCipher(SecretCipher):
    def __init__(self, delegate: SecretCipher) -> None:
        self.delegate = delegate
        self.reads = 0

    def encrypt(self, value: str) -> str:
        return self.delegate.encrypt(value)

    def decrypt(self, value: str) -> str:
        self.reads += 1
        return self.delegate.decrypt(value)


@dataclass
class AuthenticatedCrm:
    client: TestClient
    engine: Engine
    cipher: ObservedCipher
    actor: User
    other: User
    contact: UUID
    conversation: UUID
    foreign_contact: UUID
    foreign_conversation: UUID
    item: dict[str, Any]
    foreign_item: dict[str, Any]
    headers: dict[str, dict[str, str]]
    users: dict[str, UUID]

    @property
    def base(self) -> str:
        return f"/organizations/{self.actor.organization_id}/crm"

    def counts(self) -> tuple[int, ...]:
        with Session(self.engine) as session:
            return tuple(
                int(session.scalar(select(func.count()).select_from(model)) or 0)
                for model in (
                    OpportunityModel,
                    OpportunityHistoryModel,
                    OpportunityActivityModel,
                    OpportunityConversationModel,
                    CrmCustomerActivityModel,
                    ContactMergeModel,
                    AuditEventModel,
                )
            )


@pytest.fixture
def authenticated_crm(
    tmp_path: Path, monkeypatch: pytest.MonkeyPatch
) -> Generator[AuthenticatedCrm]:
    engine = create_engine(
        f"sqlite:///{tmp_path/'authorized.sqlite'}",
        connect_args={"check_same_thread": False},
    )

    @event.listens_for(engine, "connect")
    def foreign_keys(connection: Any, _: Any) -> None:
        connection.execute("PRAGMA foreign_keys=ON")

    Base.metadata.create_all(engine)
    headers, users = {}, {}
    with Session(engine) as session:
        actor, other, contact, conversation = seed(session)
        commercial = opportunity_service(session)
        cipher = ObservedCipher(commercial.cipher)
        key = commercial.digest_key
        crm = CrmService(
            session, cipher, ContactIdentityHasher(key, ContactIdentityNormalizer())
        )
        foreign_contact = crm.create(
            other.organization_id,
            other,
            CustomerCreate(display_name="Foreign customer", whatsapp="+12025550999"),
        ).id
        bot = BotModel(
            id=uuid4(),
            organization_id=other.organization_id,
            name="Foreign synthetic",
            slug="foreign",
            status="active",
        )
        session.add(bot)
        session.flush()
        foreign_conversation = uuid4()
        session.add(
            ConversationModel(
                id=foreign_conversation,
                organization_id=other.organization_id,
                bot_id=bot.id,
                contact_id=foreign_contact,
                company_id=str(other.organization_id),
                customer_id="foreign",
                channel="whatsapp",
                management_status="open",
            )
        )
        for role in ("viewer", "operator"):
            user_id = uuid4()
            session.add(
                UserModel(
                    id=user_id,
                    organization_id=actor.organization_id,
                    email=f"{role}-{user_id}@example.test",
                    role=role,
                    password_hash="test-only",
                    status="active",
                )
            )
            users[role] = user_id
        session.commit()
        users.update(admin=actor.id, foreign=other.id)
        for role, user_id in users.items():
            model = session.get(UserModel, user_id)
            assert model is not None
            headers[role] = {
                "Authorization": "Bearer "
                + get_access_token_service().create(model.id, model.auth_version)
            }
        data = payload(actor, contact, conversation)
        data.update(amount="123.45", currency="PEN")
        item = commercial.create(
            actor.organization_id, actor, OpportunityCreate.model_validate(data), "seed"
        ).model_dump(mode="json")
        foreign_item = commercial.create(
            other.organization_id,
            other,
            OpportunityCreate.model_validate(
                payload(other, foreign_contact, foreign_conversation)
            ),
            "foreign-seed",
        ).model_dump(mode="json")
        CustomerWorkspaceService(commercial).record_activity(
            actor.organization_id,
            contact,
            actor,
            ActivityInput(
                kind="note",
                description="Private activity",
                occurred_at=datetime.now(UTC),
                opportunity_id=UUID(item["id"]),
            ),
            "private-activity",
        )
    monkeypatch.setattr(
        database, "SessionLocal", sessionmaker(bind=engine, autoflush=False)
    )
    settings = get_settings().model_copy(
        update={"contact_identity_hmac_key": key, "ai_enabled": False}
    )
    for module in (crm_routes, crm_opportunity_routes):
        monkeypatch.setattr(module, "get_whatsapp_secret_cipher", lambda: cipher)
        monkeypatch.setattr(module, "get_settings", lambda: settings)
    app = create_app()
    assert not app.dependency_overrides
    try:
        with TestClient(app) as client:
            yield AuthenticatedCrm(
                client,
                engine,
                cipher,
                actor,
                other,
                contact,
                conversation,
                foreign_contact,
                foreign_conversation,
                item,
                foreign_item,
                headers,
                users,
            )
    finally:
        engine.dispose()


def test_viewer_receives_redacted_records_without_decrypting_live_content(
    authenticated_crm: AuthenticatedCrm,
) -> None:
    c = authenticated_crm
    for path in (
        c.base + "/opportunities/" + c.item["id"],
        c.base + "/opportunities",
        c.base + "/follow-up",
    ):
        c.cipher.reads = 0
        response = c.client.get(path, headers=c.headers["viewer"])
        assert response.status_code == 200, response.text
        assert c.cipher.reads == 0
        assert "Synthetic proposal" not in response.text
        assert "Private commercial need" not in response.text
        assert "Call about proposal" not in response.text
        records = response.json()
        item = records["items"][0] if "items" in records else records
        assert item["title"] == "Oportunidad"
        assert item["amount"] is None and item["currency"] is None
    for suffix in (
        "/opportunities/" + c.item["id"] + "/history",
        f"/customers/{c.contact}/workspace",
        f"/customers/{c.contact}/activities",
        f"/customers/{c.contact}/action-history",
    ):
        response = c.client.get(c.base + suffix, headers=c.headers["viewer"])
        assert response.status_code == 200, response.text
        for secret in (
            "Synthetic proposal",
            "Private commercial need",
            "Call about proposal",
            "Private activity",
        ):
            assert secret not in response.text
    response = c.client.get(
        c.base + "/opportunities/" + c.item["id"], headers=c.headers["admin"]
    )
    assert response.status_code == 200 and response.json() == c.item


def test_foreign_resources_are_absent_before_decryption(
    authenticated_crm: AuthenticatedCrm,
) -> None:
    c = authenticated_crm
    own_space = f"/organizations/{c.other.organization_id}"
    routes = (
        f"/crm/customers/{c.contact}",
        f"/crm/customers/{c.contact}/workspace",
        f"/crm/customers/{c.contact}/activities",
        f"/crm/customers/{c.contact}/action-history",
        "/crm/opportunities/" + c.item["id"],
        "/crm/opportunities/" + c.item["id"] + "/history",
        f"/conversations/{c.conversation}/commercial-context",
        f"/crm/customers/{c.contact}/suggestions/{c.conversation}",
        f"/crm/opportunities?contact_id={c.contact}",
        f"/crm/opportunities?conversation_id={c.conversation}",
    )
    before = c.counts()
    for suffix in routes:
        c.cipher.reads = 0
        response = c.client.get(own_space + suffix, headers=c.headers["foreign"])
        assert response.status_code == 404, (suffix, response.text)
        assert c.cipher.reads == 0
        assert "Synthetic proposal" not in response.text
    for suffix in (
        "/customers",
        "/opportunities",
        "/duplicates",
        "/stages",
        "/sales-metrics",
    ):
        c.cipher.reads = 0
        response = c.client.get(c.base + suffix, headers=c.headers["foreign"])
        assert response.status_code == 403, (suffix, response.text)
        assert c.cipher.reads == 0
    assert c.counts() == before


def test_foreign_references_cannot_write_or_link(
    authenticated_crm: AuthenticatedCrm,
) -> None:
    c = authenticated_crm
    data = payload(c.actor, c.contact, c.conversation)
    before = c.counts()
    for field, value, status in (
        ("contact_id", c.foreign_contact, 404),
        ("conversation_id", c.foreign_conversation, 404),
        ("assigned_user_id", c.other.id, 400),
    ):
        response = c.client.post(
            c.base + "/opportunities",
            json={**data, field: str(value)},
            headers={**c.headers["admin"], "Idempotency-Key": "foreign-" + field},
        )
        assert response.status_code == status, response.text
    assert (
        c.client.put(
            c.base
            + f"/opportunities/{c.item['id']}/conversations/{c.foreign_conversation}",
            headers=c.headers["admin"],
        ).status_code
        == 404
    )
    assert (
        c.client.post(
            c.base + f"/customers/{c.contact}/activities",
            json=dict(
                kind="note",
                description="Rejected foreign reference",
                occurred_at=datetime.now(UTC).isoformat(),
                opportunity_id=c.foreign_item["id"],
            ),
            headers={**c.headers["admin"], "Idempotency-Key": "foreign-activity"},
        ).status_code
        == 404
    )
    assert (
        c.client.get(
            c.base
            + f"/merge-preview?source_id={c.contact}&target_id={c.foreign_contact}",
            headers=c.headers["admin"],
        ).status_code
        == 404
    )
    assert (
        c.client.post(
            c.base + "/customer-merges",
            json=dict(
                source_id=str(c.contact),
                target_id=str(c.foreign_contact),
                review_token="0" * 64,
            ),
            headers=c.headers["admin"],
        ).status_code
        == 404
    )
    assert c.counts() == before
    assert (
        c.client.get(
            c.base + "/opportunities/" + c.item["id"], headers=c.headers["admin"]
        ).json()
        == c.item
    )


def test_permission_changes_and_account_revocation_apply_to_existing_token(
    authenticated_crm: AuthenticatedCrm,
) -> None:
    c = authenticated_crm
    url = c.base + "/opportunities/" + c.item["id"]
    with Session(c.engine) as session:
        model = session.get(UserModel, c.actor.id)
        assert model is not None
        model.role = "viewer"
        session.commit()
    c.cipher.reads = 0
    response = c.client.get(url, headers=c.headers["admin"])
    assert response.status_code == 200 and response.json()["need"] is None
    assert c.cipher.reads == 0
    data = payload(c.actor, c.contact, c.conversation)
    before = c.counts()
    # Permission is rechecked even for a valid replay of an existing key.
    data.update(amount="123.45", currency="PEN")
    assert (
        c.client.post(
            c.base + "/opportunities",
            json=data,
            headers={**c.headers["admin"], "Idempotency-Key": "seed"},
        ).status_code
        == 403
    )
    assert c.counts() == before
    with Session(c.engine) as session:
        model = session.get(UserModel, c.actor.id)
        assert model is not None
        model.role = "organization_admin"
        model.status = "inactive"
        session.commit()
    assert c.client.get(url, headers=c.headers["admin"]).status_code == 403
    with Session(c.engine) as session:
        model = session.get(UserModel, c.actor.id)
        organization = session.get(OrganizationModel, c.actor.organization_id)
        assert model is not None and organization is not None
        model.status = "active"
        organization.status = "inactive"
        session.commit()
    assert c.client.get(url, headers=c.headers["admin"]).status_code == 403
    with Session(c.engine) as session:
        model = session.get(UserModel, c.actor.id)
        organization = session.get(OrganizationModel, c.actor.organization_id)
        assert model is not None and organization is not None
        organization.status = "active"
        model.auth_version += 1
        session.commit()
    assert c.client.get(url, headers=c.headers["admin"]).status_code == 401
    c.cipher.reads = 0
    assert c.client.get(url, headers=c.headers["admin"]).status_code == 401
    assert c.cipher.reads == 0


def test_signed_role_and_tenant_claims_cannot_override_persisted_membership(
    authenticated_crm: AuthenticatedCrm,
) -> None:
    c = authenticated_crm
    settings = get_settings()
    claims = dict(
        sub=str(c.users["viewer"]),
        auth_version=1,
        exp=datetime.now(UTC) + timedelta(minutes=5),
        role="platform_admin",
        organization_id=str(c.other.organization_id),
    )
    signed = jwt.encode(claims, settings.auth_secret_key, algorithm="HS256")
    headers = {"Authorization": "Bearer " + signed}
    response = c.client.get(c.base + "/opportunities/" + c.item["id"], headers=headers)
    assert response.status_code == 200 and response.json()["need"] is None
    assert (
        c.client.get(
            c.base + "/customers?search_by=phone&search=%2B12025550147", headers=headers
        ).status_code
        == 403
    )
    assert (
        c.client.get(
            f"/organizations/{c.other.organization_id}/crm/customers", headers=headers
        ).status_code
        == 403
    )
    variants = (
        jwt.encode(
            claims,
            "incorrect-secret-only-for-test-at-least-thirty-two",
            algorithm="HS256",
        ),
        jwt.encode(claims, "", algorithm="none"),
        jwt.encode(
            {**claims, "exp": datetime.now(UTC) - timedelta(minutes=1)},
            settings.auth_secret_key,
            algorithm="HS256",
        ),
        jwt.encode(
            {k: v for k, v in claims.items() if k != "auth_version"},
            settings.auth_secret_key,
            algorithm="HS256",
        ),
        jwt.encode(
            {**claims, "sub": str(uuid4())}, settings.auth_secret_key, algorithm="HS256"
        ),
    )
    for token in variants:
        c.cipher.reads = 0
        response = c.client.get(
            c.base + "/customers", headers={"Authorization": "Bearer " + token}
        )
        assert response.status_code == 401, response.text
        assert c.cipher.reads == 0
    assert c.client.get(c.base + "/customers").status_code == 401


def test_operator_can_edit_but_cannot_escalate_sensitive_or_admin_permissions(
    authenticated_crm: AuthenticatedCrm,
) -> None:
    c = authenticated_crm
    for role in ("operator", "viewer"):
        for suffix in (
            "/customers?search_by=phone&search=%2B12025550147",
            "/customers?search_by=email&search=test%40example.test",
            "/customers?identifier=%2B12025550147",
            "/duplicates",
            f"/merge-preview?source_id={c.contact}&target_id={c.foreign_contact}",
        ):
            c.cipher.reads = 0
            assert (
                c.client.get(c.base + suffix, headers=c.headers[role]).status_code
                == 403
            )
            assert c.cipher.reads == 0
    stages = c.client.get(c.base + "/stages", headers=c.headers["admin"]).json()
    for role in ("operator", "viewer"):
        assert (
            c.client.put(
                c.base + "/stages",
                json={"stages": stages, "expected_stages": stages},
                headers=c.headers[role],
            ).status_code
            == 403
        )
    data = {
        k: v
        for k, v in payload(c.actor, c.contact, c.conversation).items()
        if k not in {"contact_id", "conversation_id"}
    }
    data.update(version=1, stage_code="offer")
    before = c.counts()
    assert (
        c.client.patch(
            c.base + "/opportunities/" + c.item["id"],
            json=data,
            headers=c.headers["viewer"],
        ).status_code
        == 403
    )
    assert (
        c.client.get(
            c.base + f"/customers/{c.contact}/suggestions/{c.conversation}",
            headers=c.headers["viewer"],
        ).status_code
        == 403
    )
    assert c.counts() == before
    response = c.client.patch(
        c.base + "/opportunities/" + c.item["id"],
        json=data,
        headers=c.headers["operator"],
    )
    assert response.status_code == 200 and response.json()["version"] == 2
    assert (
        len(
            c.client.get(
                c.base + "/opportunities/" + c.item["id"] + "/history",
                headers=c.headers["operator"],
            ).json()
        )
        == 2
    )
