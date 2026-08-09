import base64
import hashlib
import hmac
from collections.abc import Generator
from dataclasses import dataclass
from typing import cast
from uuid import UUID, uuid4

import pytest
from app.api.dependencies import (
    get_bot_service,
    get_organization_service,
    get_user_service,
)
from app.api.whatsapp_configuration_dependencies import (
    get_whatsapp_configuration_service,
    get_whatsapp_webhook_validation_service,
)
from app.application.bots.service import BotService
from app.application.channel.resolver import ChannelResolutionError
from app.application.organizations.service import OrganizationService
from app.application.users.service import UserService
from app.application.whatsapp_configuration.resolver import (
    WhatsAppChannelResolver,
)
from app.application.whatsapp_configuration.service import (
    WhatsAppConfigurationService,
)
from app.application.whatsapp_configuration.signature import (
    WhatsAppWebhookSignatureVerifier,
)
from app.application.whatsapp_configuration.webhook import (
    WhatsAppWebhookValidationService,
)
from app.infrastructure.database import Base
from app.infrastructure.models.whatsapp_channel_configuration import (
    WhatsAppChannelConfigurationModel,
)
from app.infrastructure.repositories.audit_repository import SqlAlchemyAuditRepository
from app.infrastructure.repositories.bot_repository import BotRepository
from app.infrastructure.repositories.organization_repository import (
    OrganizationRepository,
)
from app.infrastructure.repositories.user_repository import UserRepository
from app.infrastructure.repositories.whatsapp_configuration_repository import (
    SqlAlchemyWhatsAppConfigurationRepository,
)
from app.main import create_app
from app.security.passwords import PasswordService
from app.security.secret_cipher import EnvironmentSecretCipher
from argon2 import PasswordHasher
from fastapi.testclient import TestClient
from httpx import Response
from sqlalchemy import create_engine
from sqlalchemy.orm import Session, sessionmaker
from sqlalchemy.pool import StaticPool


@dataclass(frozen=True)
class Runtime:
    client: TestClient
    session: Session
    cipher: EnvironmentSecretCipher


@pytest.fixture
def runtime() -> Generator[Runtime]:
    engine = create_engine(
        "sqlite:///:memory:",
        connect_args={"check_same_thread": False},
        poolclass=StaticPool,
    )
    Base.metadata.create_all(engine)
    session = sessionmaker(bind=engine)()
    cipher_key = base64.urlsafe_b64encode(b"w" * 32).decode("ascii")
    cipher = EnvironmentSecretCipher(cipher_key)
    password_service = PasswordService(
        hasher=PasswordHasher(time_cost=1, memory_cost=1024, parallelism=1),
    )

    def organization_service() -> OrganizationService:
        return OrganizationService(
            OrganizationRepository(session),
            session,
            SqlAlchemyAuditRepository(session),
        )

    def user_service() -> UserService:
        return UserService(
            UserRepository(session),
            OrganizationRepository(session),
            password_service,
            session,
            SqlAlchemyAuditRepository(session),
        )

    def bot_service() -> BotService:
        return BotService(
            BotRepository(session),
            OrganizationRepository(session),
            session,
            SqlAlchemyAuditRepository(session),
        )

    def whatsapp_service() -> WhatsAppConfigurationService:
        return WhatsAppConfigurationService(
            SqlAlchemyWhatsAppConfigurationRepository(session),
            BotRepository(session),
            OrganizationRepository(session),
            cipher,
            session,
        )

    def webhook_service() -> WhatsAppWebhookValidationService:
        return WhatsAppWebhookValidationService(
            SqlAlchemyWhatsAppConfigurationRepository(session),
            cipher,
            WhatsAppWebhookSignatureVerifier(),
        )

    app = create_app()
    app.dependency_overrides[get_organization_service] = organization_service
    app.dependency_overrides[get_user_service] = user_service
    app.dependency_overrides[get_bot_service] = bot_service
    app.dependency_overrides[get_whatsapp_configuration_service] = whatsapp_service
    app.dependency_overrides[get_whatsapp_webhook_validation_service] = webhook_service
    try:
        with TestClient(app) as client:
            yield Runtime(client, session, cipher)
    finally:
        session.close()
        app.dependency_overrides.clear()


def auth(token: str) -> dict[str, str]:
    return {"Authorization": f"Bearer {token}"}


def create_org(client: TestClient, slug: str) -> str:
    response = client.post("/organizations", json={"name": slug, "slug": slug})
    assert response.status_code == 201
    return str(response.json()["organization"]["id"])


def create_user(
    client: TestClient,
    organization_id: str,
    email: str,
    *,
    token: str | None = None,
    role: str | None = None,
) -> dict[str, object]:
    payload: dict[str, object] = {
        "organization_id": organization_id,
        "email": email,
        "password": "valid-password-123",
    }
    if role is not None:
        payload["role"] = role
    response = client.post(
        "/users",
        json=payload,
        headers=auth(token) if token else None,
    )
    assert response.status_code == 201
    return dict(response.json()["user"])


def login(client: TestClient, email: str) -> str:
    response = client.post(
        "/auth/login",
        json={"email": email, "password": "valid-password-123"},
    )
    assert response.status_code == 200
    return str(response.json()["access_token"])


def create_bot(client: TestClient, token: str, slug: str) -> dict[str, object]:
    response = client.post(
        "/bots",
        json={"name": slug, "slug": slug},
        headers=auth(token),
    )
    assert response.status_code == 201
    return dict(response.json()["bot"])


def create_configuration(
    client: TestClient,
    base: str,
    token: str,
    *,
    phone_number_id: str,
    display_name: str = "Support channel",
) -> Response:
    return cast(
        Response,
        client.post(
            base,
            json={
                "display_name": display_name,
                "phone_number_id": phone_number_id,
                "whatsapp_business_account_id": f"waba-{phone_number_id}",
            },
            headers=auth(token),
        ),
    )


def make_platform_admin(runtime: Runtime, email: str) -> str:
    model = UserRepository(runtime.session).find_by_email(email)
    assert model is not None
    model.role = "platform_admin"
    runtime.session.commit()
    return login(runtime.client, email)


def test_lifecycle_secrets_rbac_webhook_and_resolver(runtime: Runtime) -> None:
    client = runtime.client
    organization_id = create_org(client, "prd007-acme")
    create_user(client, organization_id, "owner@example.com")
    owner_token = login(client, "owner@example.com")
    operator = create_user(
        client,
        organization_id,
        "operator@example.com",
        token=owner_token,
        role="operator",
    )
    viewer = create_user(
        client,
        organization_id,
        "viewer@example.com",
        token=owner_token,
    )
    operator_token = login(client, str(operator["email"]))
    viewer_token = login(client, str(viewer["email"]))
    bot = create_bot(client, owner_token, "support")
    base = (
        f"/organizations/{organization_id}/bots/{bot['id']}" "/whatsapp-configurations"
    )

    created = create_configuration(
        client,
        base,
        operator_token,
        phone_number_id="phone-100",
    )
    assert created.status_code == 201
    configuration = created.json()["configuration"]
    configuration_id = configuration["id"]
    public_webhook_id = configuration["public_webhook_id"]
    assert configuration["status"] == "draft"
    assert not configuration["verify_token_configured"]
    assert "ciphertext" not in created.text
    assert "verify-token" not in created.text

    operator_secret_create = client.post(
        base,
        json={
            "display_name": "Sensitive",
            "phone_number_id": "phone-sensitive",
            "whatsapp_business_account_id": "waba-sensitive",
            "verify_token": "forbidden",
        },
        headers=auth(operator_token),
    )
    draft_resolution = WhatsAppChannelResolver(
        SqlAlchemyWhatsAppConfigurationRepository(runtime.session),
    )
    with pytest.raises(ChannelResolutionError):
        draft_resolution.resolve("phone-100")

    incomplete_activation = client.post(
        f"{base}/{configuration_id}/activate",
        headers=auth(owner_token),
    )
    operator_rotate = client.post(
        f"{base}/{configuration_id}/rotate-secrets",
        json={"verify_token": "blocked"},
        headers=auth(operator_token),
    )
    first_rotation = client.post(
        f"{base}/{configuration_id}/rotate-secrets",
        json={
            "verify_token": "verify-token",
            "access_token": "access-token",
            "app_secret": "app-secret",
        },
        headers=auth(owner_token),
    )
    model = runtime.session.get(
        WhatsAppChannelConfigurationModel,
        UUID(configuration_id),
    )
    assert model is not None
    original_verify_ciphertext = model.verify_token_ciphertext
    assert original_verify_ciphertext != "verify-token"
    assert runtime.cipher.decrypt(str(original_verify_ciphertext)) == "verify-token"

    second_rotation = client.post(
        f"{base}/{configuration_id}/rotate-secrets",
        json={"verify_token": "rotated-token"},
        headers=auth(owner_token),
    )
    runtime.session.refresh(model)
    assert model.verify_token_ciphertext != original_verify_ciphertext
    assert runtime.cipher.decrypt(str(model.verify_token_ciphertext)) == "rotated-token"

    activated = client.post(
        f"{base}/{configuration_id}/activate",
        headers=auth(owner_token),
    )
    invalid_activation = client.post(
        f"{base}/{configuration_id}/activate",
        headers=auth(owner_token),
    )
    viewer_read = client.get(
        f"{base}/{configuration_id}",
        headers=auth(viewer_token),
    )
    viewer_update = client.patch(
        f"{base}/{configuration_id}",
        json={"display_name": "Blocked"},
        headers=auth(viewer_token),
    )
    operator_update = client.patch(
        f"{base}/{configuration_id}",
        json={"display_name": "Updated support"},
        headers=auth(operator_token),
    )
    listed = client.get(
        f"{base}?status=active&phone_number_id=phone-100"
        "&search=Updated&page=1&page_size=1",
        headers=auth(viewer_token),
    )

    resolved = draft_resolution.resolve("phone-100")
    assert resolved.organization_id == UUID(organization_id)
    assert resolved.bot_id == UUID(str(bot["id"]))

    challenge = client.get(
        f"/webhooks/whatsapp/{public_webhook_id}",
        params={
            "hub.mode": "subscribe",
            "hub.verify_token": "rotated-token",
            "hub.challenge": "challenge-123",
        },
    )
    wrong_challenge = client.get(
        f"/webhooks/whatsapp/{public_webhook_id}",
        params={
            "hub.mode": "subscribe",
            "hub.verify_token": "wrong",
            "hub.challenge": "challenge-123",
        },
    )
    raw_body = b'{"configuration":"validation-only"}'
    signature = (
        "sha256="
        + hmac.new(
            b"app-secret",
            raw_body,
            hashlib.sha256,
        ).hexdigest()
    )
    signature_valid = client.post(
        f"/webhooks/whatsapp/{public_webhook_id}/validate-signature",
        content=raw_body,
        headers={"X-Hub-Signature-256": signature},
    )
    signature_invalid = client.post(
        f"/webhooks/whatsapp/{public_webhook_id}/validate-signature",
        content=raw_body,
        headers={"X-Hub-Signature-256": "sha256=invalid"},
    )

    deactivated = client.post(
        f"{base}/{configuration_id}/deactivate",
        headers=auth(owner_token),
    )
    with pytest.raises(ChannelResolutionError):
        draft_resolution.resolve("phone-100")
    inactive_challenge = client.get(
        f"/webhooks/whatsapp/{public_webhook_id}",
        params={
            "hub.mode": "subscribe",
            "hub.verify_token": "rotated-token",
            "hub.challenge": "challenge-123",
        },
    )
    reactivated = client.post(
        f"{base}/{configuration_id}/activate",
        headers=auth(owner_token),
    )

    assert operator_secret_create.status_code == 403
    assert incomplete_activation.status_code == 409
    assert operator_rotate.status_code == 403
    assert first_rotation.status_code == 200
    assert second_rotation.status_code == 200
    assert activated.status_code == 200
    assert invalid_activation.status_code == 409
    assert viewer_read.status_code == 200
    assert "ciphertext" not in viewer_read.text
    assert "rotated-token" not in viewer_read.text
    assert viewer_update.status_code == 403
    assert operator_update.status_code == 200
    assert listed.status_code == 200
    assert listed.json()["total"] == 1
    assert challenge.status_code == 200
    assert challenge.text == "challenge-123"
    assert wrong_challenge.status_code == 403
    assert signature_valid.status_code == 200
    assert signature_invalid.status_code == 403
    assert deactivated.status_code == 200
    assert inactive_challenge.status_code == 403
    assert reactivated.status_code == 200


def test_tenant_uniqueness_platform_admin_and_delete(
    runtime: Runtime,
    monkeypatch: pytest.MonkeyPatch,
) -> None:
    client = runtime.client
    org_a = create_org(client, "alpha-seven")
    org_b = create_org(client, "beta-seven")
    create_user(client, org_a, "owner-a@example.com")
    create_user(client, org_b, "owner-b@example.com")
    token_a = login(client, "owner-a@example.com")
    token_b = login(client, "owner-b@example.com")
    platform = create_user(
        client,
        org_a,
        "platform@example.com",
        token=token_a,
    )
    inactive = create_user(
        client,
        org_a,
        "inactive@example.com",
        token=token_a,
    )
    inactive_token = login(client, str(inactive["email"]))
    bot_a = create_bot(client, token_a, "alpha-bot-seven")
    bot_b = create_bot(client, token_b, "beta-bot-seven")
    base_a = f"/organizations/{org_a}/bots/{bot_a['id']}/whatsapp-configurations"
    base_b = f"/organizations/{org_b}/bots/{bot_b['id']}/whatsapp-configurations"
    created_a = create_configuration(
        client,
        base_a,
        token_a,
        phone_number_id="globally-unique-phone",
    )
    configuration_a = created_a.json()["configuration"]
    created_b = create_configuration(
        client,
        base_b,
        token_b,
        phone_number_id="beta-phone",
    )
    configuration_b = created_b.json()["configuration"]

    cross = client.get(
        f"{base_a}/{configuration_a['id']}",
        headers=auth(token_b),
    )
    wrong_bot = client.get(
        f"/organizations/{org_a}/bots/{bot_b['id']}"
        f"/whatsapp-configurations/{configuration_a['id']}",
        headers=auth(token_a),
    )
    duplicate_phone = create_configuration(
        client,
        base_b,
        token_b,
        phone_number_id="globally-unique-phone",
    )

    existing_public_id = UUID(str(configuration_a["public_webhook_id"]))
    generated_ids = iter((uuid4(), existing_public_id))
    monkeypatch.setattr(
        "app.application.whatsapp_configuration.service.uuid4",
        lambda: next(generated_ids),
    )
    duplicate_webhook = create_configuration(
        client,
        base_b,
        token_b,
        phone_number_id="another-phone",
    )

    platform_token = make_platform_admin(runtime, str(platform["email"]))
    platform_cross_read = client.get(
        f"{base_b}/{configuration_b['id']}",
        headers=auth(platform_token),
    )
    client.post(
        f"/users/{inactive['id']}/deactivate",
        headers=auth(platform_token),
    )
    inactive_read = client.get(base_a, headers=auth(inactive_token))
    deleted = client.delete(
        f"{base_b}/{configuration_b['id']}",
        headers=auth(token_b),
    )
    deleted_read = client.get(
        f"{base_b}/{configuration_b['id']}",
        headers=auth(token_b),
    )

    assert cross.status_code == 403
    assert wrong_bot.status_code == 404
    assert duplicate_phone.status_code == 409
    assert duplicate_webhook.status_code == 409
    assert platform_cross_read.status_code == 200
    assert inactive_read.status_code == 403
    assert deleted.status_code == 204
    assert deleted_read.status_code == 404
