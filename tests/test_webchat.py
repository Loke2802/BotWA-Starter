"""Visitor capability and managed inbox tests; no external calls or paid AI."""

from collections.abc import Generator
from contextlib import contextmanager
from dataclasses import dataclass
from datetime import UTC, datetime, timedelta
from typing import cast
from uuid import UUID, uuid4

import pytest
from app.api.dependencies import require_authenticated_user
from app.api.human_handoff_dependencies import get_human_handoff_service
from app.api.human_handoff_routes import router as handoff_router
from app.api.security_dependencies import get_rate_limit_service
from app.api.webchat_dependencies import (
    get_webchat_service,
    get_webchat_service_factory,
)
from app.api.webchat_routes import create_webchat_app, install_webchat, webchat_origins
from app.api.whatsapp_live_dependencies import get_whatsapp_live_message_processor
from app.application.human_handoff.service import HumanHandoffService
from app.application.webchat.service import WebchatService
from app.application.whatsapp_live.processor import WhatsAppLiveMessageProcessor
from app.domain.user.contracts import User
from app.infrastructure.database import Base
from app.infrastructure.models.bot import BotModel
from app.infrastructure.models.business_configuration import BusinessConfigurationModel
from app.infrastructure.models.conversation import ConversationModel
from app.infrastructure.models.knowledge_entry import KnowledgeEntryModel
from app.infrastructure.models.message import MessageModel
from app.infrastructure.models.organization import OrganizationModel
from app.infrastructure.models.user import UserModel
from app.infrastructure.repositories.audit_repository import SqlAlchemyAuditRepository
from app.infrastructure.repositories.human_handoff_repository import (
    HumanHandoffRepository,
)
from app.infrastructure.settings import Environment, Settings
from app.security.rate_limit import InMemoryRateLimitRepository, RateLimitService
from app.security.secret_cipher import EnvironmentSecretCipher
from cryptography.fernet import Fernet
from fastapi import FastAPI
from fastapi.testclient import TestClient
from httpx import Response
from sqlalchemy import Engine, create_engine, select
from sqlalchemy.orm import Session, sessionmaker
from sqlalchemy.pool import StaticPool

from tests.plan_support import allow_all_plan_enforcement

ORIGIN = "https://kalivur.com"


@dataclass
class Runtime:
    client: TestClient
    session: Session
    service: WebchatService
    settings: Settings
    actor: User
    app: FastAPI

    def post(
        self,
        path: str,
        token: str = "",
        body: dict[str, object] | None = None,
        origin: str = ORIGIN,
    ) -> Response:
        return cast(
            Response,
            self.client.post(
                path,
                json=body or {},
                headers={
                    "Origin": origin,
                    "Authorization": f"Bearer {token}",
                },
            ),
        )

    def token(self) -> str:
        response = self.post("/sessions")
        assert response.status_code == 200, response.text
        return str(response.json()["token"])


@pytest.fixture
def webchat_engine() -> Generator[Engine]:
    engine = create_engine(
        "sqlite://", connect_args={"check_same_thread": False}, poolclass=StaticPool
    )
    yield engine
    engine.dispose()


@contextmanager
def webchat_runtime(engine: Engine) -> Generator[Runtime]:
    Base.metadata.create_all(engine)
    session = sessionmaker(bind=engine)()
    org_id, bot_id, user_id = uuid4(), uuid4(), uuid4()
    session.add_all(
        [
            OrganizationModel(
                id=org_id, name="Example", slug=str(org_id), status="active"
            ),
            BotModel(
                id=bot_id,
                organization_id=org_id,
                name="Example",
                slug="bot",
                status="active",
            ),
            UserModel(
                id=user_id,
                organization_id=org_id,
                email="owner@example.com",
                password_hash="unused",
                role="organization_owner",
                status="active",
            ),
            BusinessConfigurationModel(
                bot_id=bot_id,
                business_name="Example",
                description="Test",
                service_instructions="Test",
                handoff_enabled=True,
            ),
        ]
    )
    session.commit()
    session.add_all(
        [
            KnowledgeEntryModel(
                organization_id=org_id,
                bot_id=bot_id,
                title="Web",
                content="Example desarrolla páginas web.",
                status="published",
                created_by_user_id=user_id,
            ),
            KnowledgeEntryModel(
                organization_id=org_id,
                bot_id=bot_id,
                title="Borrador",
                content="Unicornio cuesta 999.",
                status="draft",
                created_by_user_id=user_id,
            ),
        ]
    )
    session.commit()
    settings = Settings(
        _env_file=None,
        environment=Environment.TEST,
        webchat_enabled=True,
        webchat_organization_id=org_id,
        webchat_bot_id=bot_id,
        webchat_origins=ORIGIN,
    )
    cipher = EnvironmentSecretCipher(Fernet.generate_key().decode())
    handoff = HumanHandoffService(
        HumanHandoffRepository(session),
        session,
        SqlAlchemyAuditRepository(session),
        allow_all_plan_enforcement(),
    )
    service = WebchatService(
        session, settings, cipher, handoff, allow_all_plan_enforcement()
    )
    limiter = RateLimitService(
        InMemoryRateLimitRepository(), hmac_key="webchat-test-only"
    )
    app = create_webchat_app(settings)
    app.include_router(handoff_router)
    app.dependency_overrides[get_webchat_service] = lambda: service
    app.dependency_overrides[get_webchat_service_factory] = lambda: lambda: service
    app.dependency_overrides[get_rate_limit_service] = lambda: limiter
    app.dependency_overrides[get_human_handoff_service] = lambda: handoff
    # No WhatsApp sender may be used for this web channel. An object deliberately
    # lacking send_human_reply makes accidental transport use fail immediately.
    app.dependency_overrides[get_whatsapp_live_message_processor] = lambda: cast(
        WhatsAppLiveMessageProcessor, object()
    )
    actor = User(
        id=user_id,
        organization_id=org_id,
        email="owner@example.com",
        role="organization_owner",
    )
    app.dependency_overrides[require_authenticated_user] = lambda: actor
    with TestClient(app) as client:
        yield Runtime(client, session, service, settings, actor, app)
    session.close()


@pytest.fixture
def webchat(webchat_engine: Engine) -> Generator[Runtime]:
    with webchat_runtime(webchat_engine) as runtime:
        yield runtime


def test_encrypted_persisted_history_idempotency(webchat: Runtime) -> None:
    token = webchat.token()
    body: dict[str, object] = {
        "message": "Quiero una web",
        "idempotency_key": str(uuid4()),
    }
    response = webchat.post("/messages", token, body)
    assert response.status_code == 200, response.text
    assert [item["text"] for item in response.json()["messages"]] == [
        "Quiero una web",
        "Example desarrolla páginas web.",
    ]
    assert webchat.post("/messages", token, body).json() == response.json()
    assert (
        webchat.post("/messages", token, {**body, "message": "Otro"}).status_code == 409
    )
    rows = list(webchat.session.scalars(select(MessageModel)).all())
    assert len(rows) == 2
    assert all(
        item.content == "" and "Quiero" not in (item.text_ciphertext or "")
        for item in rows
    )
    conversation = webchat.session.get(ConversationModel, UUID(token.split(".")[0]))
    assert conversation is not None and token not in str(conversation.extra_data)
    assert conversation.message_count == 2
    # Recreate application service and ORM session, retaining only the database.
    with Session(webchat.session.get_bind()) as restarted:
        service = WebchatService(
            restarted,
            webchat.settings,
            webchat.service.cipher,
            webchat.service.handoff,
            allow_all_plan_enforcement(),
        )
        assert service.history(token, ORIGIN).model_dump(mode="json") == response.json()


def test_isolation_and_revocation(webchat: Runtime) -> None:
    first, second = webchat.token(), webchat.token()
    assert webchat.post("/history", first + "x").status_code == 401
    forged = first.split(".")[0] + "." + second.split(".")[1]
    assert webchat.post("/history", forged).status_code == 401
    assert (
        webchat.post("/history", first, origin="https://foreign.example").status_code
        == 403
    )
    assert (
        webchat.post("/sessions", body={"organization_id": str(uuid4())}).status_code
        == 422
    )
    assert webchat.post("/close", first).status_code == 200
    assert webchat.post("/history", first).status_code == 401
    assert webchat.post("/history", second).json()["messages"] == []
    webchat.settings.webchat_bot_id = uuid4()
    assert webchat.post("/history", second).status_code == 503


def test_expiry_inactive_scope_and_disable(webchat: Runtime) -> None:
    token = webchat.token()
    row = webchat.session.get(ConversationModel, UUID(token.split(".")[0]))
    assert row is not None
    row.extra_data = {
        **(row.extra_data or {}),
        "webchat_expires_at": (datetime.now(UTC) - timedelta(seconds=1)).isoformat(),
    }
    webchat.session.commit()
    assert webchat.post("/history", token).status_code == 401
    bot = webchat.session.get(BotModel, webchat.settings.webchat_bot_id)
    assert bot is not None
    bot.status = "inactive"
    webchat.session.commit()
    assert webchat.post("/sessions").status_code == 503
    bot.status = "active"
    webchat.session.commit()
    webchat.settings.webchat_enabled = False
    assert webchat.post("/history", token).status_code == 503


def test_only_published_knowledge(webchat: Runtime) -> None:
    token = webchat.token()
    response = webchat.post(
        "/messages", token, {"message": "Unicornio", "idempotency_key": str(uuid4())}
    )
    assert response.status_code == 200
    assert "No tengo información" in response.json()["messages"][-1]["text"]
    assert "999" not in response.text


def test_handoff_operator_round_trip_and_authorization(webchat: Runtime) -> None:
    token = webchat.token()
    assert webchat.post("/handoff", token).json()["status"] == "waiting_human"
    assert webchat.post("/handoff", token).json()["status"] == "waiting_human"
    response = webchat.post(
        "/messages", token, {"message": "web", "idempotency_key": str(uuid4())}
    )
    assert len(response.json()["messages"]) == 1  # No automated reply during handoff.
    conversation_id = UUID(token.split(".")[0])
    path = (
        f"/organizations/{webchat.actor.organization_id}/conversations/"
        f"{conversation_id}/handoff"
    )
    payload: dict[str, object] = {
        "text": "Hola, te atiende una persona.",
        "idempotency_key": "web-operator-test-001",
    }
    assert webchat.post(path + "/messages", body=payload).status_code == 409
    assert webchat.post(path + "/claim").status_code == 200
    sent = webchat.post(path + "/messages", body=payload)
    assert sent.status_code == 200, sent.text
    assert webchat.post(path + "/messages", body=payload).json() == sent.json()
    assert webchat.post("/history", token).json()["messages"][-1] == {
        "id": sent.json()["attempt_id"],
        "role": "operator",
        "text": payload["text"],
    }
    assert (
        webchat.post(
            path + "/messages", body={**payload, "text": "distinto"}
        ).status_code
        == 409
    )
    foreign = User(
        organization_id=uuid4(), email="foreign@example.com", role="organization_owner"
    )
    webchat.app.dependency_overrides[require_authenticated_user] = lambda: foreign
    assert webchat.post(path + "/messages", body=payload).status_code == 403


def test_bounds_rate_limit_and_headers(webchat: Runtime) -> None:
    assert webchat.post("/sessions").headers["cache-control"] == "no-store"
    token = webchat.token()
    for value in ["", "  ", "x" * 1501]:
        assert (
            webchat.post(
                "/messages", token, {"message": value, "idempotency_key": str(uuid4())}
            ).status_code
            == 422
        )
    assert webchat.post("/messages", token, {"message": "x" * 9000}).status_code == 413
    for _ in range(4):
        assert webchat.post("/sessions").status_code == 200
    assert webchat.post("/sessions").status_code == 429
    assert (
        webchat.client.options(
            "/sessions",
            headers={
                "Origin": ORIGIN,
                "Access-Control-Request-Method": "POST",
                "Access-Control-Request-Headers": "authorization,content-type",
            },
        ).status_code
        == 200
    )


def test_defaults_disabled_and_invalid_origins(monkeypatch: pytest.MonkeyPatch) -> None:
    monkeypatch.delenv("BOTWA_WEBCHAT_ENABLED", raising=False)
    app = FastAPI()
    install_webchat(app)
    assert TestClient(app).post("/webchat/sessions", json={}).status_code == 404
    for origin in [
        "*",
        "https://kalivur.com/path",
        "http://kalivur.com",
        "https://user:pass@kalivur.com",
    ]:
        with pytest.raises(ValueError):
            webchat_origins(
                Settings(
                    _env_file=None,
                    webchat_origins=origin,
                    webchat_organization_id=uuid4(),
                    webchat_bot_id=uuid4(),
                )
            )


def test_disabled_handoff_and_plan_fail_closed(webchat: Runtime) -> None:
    from app.application.plans.service import PlanEnforcementService
    from app.infrastructure.repositories.plan_repository import SqlAlchemyPlanRepository

    token = webchat.token()
    configuration = webchat.session.scalar(select(BusinessConfigurationModel))
    assert configuration is not None
    configuration.handoff_enabled = False
    webchat.session.commit()
    assert webchat.post("/handoff", token).status_code == 409
    webchat.service.plans = PlanEnforcementService(
        SqlAlchemyPlanRepository(webchat.session)
    )
    # No assignment exists: the public channel must not bypass entitlement checks.
    assert webchat.post("/sessions").status_code == 409
    assert (
        webchat.post(
            "/messages",
            token,
            {
                "message": "web",
                "idempotency_key": str(uuid4()),
            },
        ).status_code
        == 409
    )
    assert not webchat.session.scalars(select(MessageModel)).all()


def test_wrong_tenant_or_channel_cannot_read(webchat: Runtime) -> None:
    token = webchat.token()
    row = webchat.session.get(ConversationModel, UUID(token.split(".")[0]))
    assert row is not None
    row.channel = "whatsapp"
    webchat.session.commit()
    assert webchat.post("/history", token).status_code == 401
    row.channel = "web"
    row.organization_id = uuid4()
    webchat.session.commit()
    assert webchat.post("/history", token).status_code == 401


def test_handoff_resolution_and_session_bounds(webchat: Runtime) -> None:
    token = webchat.token()
    identifier = UUID(token.split(".")[0])
    row = webchat.session.get(ConversationModel, identifier)
    assert row is not None
    row.message_count = 200
    webchat.session.commit()
    payload: dict[str, object] = {"message": "web", "idempotency_key": str(uuid4())}
    assert webchat.post("/messages", token, payload).status_code == 409
    row.message_count = 0
    webchat.session.commit()
    assert webchat.post("/handoff", token).status_code == 200
    org = webchat.actor.organization_id
    webchat.service.handoff.claim(org, identifier, webchat.actor)
    webchat.service.handoff.resolve(org, identifier, webchat.actor, return_to_bot=False)
    assert webchat.post("/messages", token, payload).status_code == 409
    assert webchat.post("/history", token).json()["status"] == "resolved"
