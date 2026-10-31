"""Load one access token into the draft staging test channel through hidden input.

Read-only by default. --apply requires an interactive TTY and human confirmation.
No remote Meta calls, activation, webhook changes, token generation or sends.
"""

import argparse
import getpass
import json
import os
import sys
import warnings
from datetime import datetime
from uuid import UUID

from app.application.plans.service import PlanEnforcementService
from app.application.whatsapp_configuration.service import WhatsAppConfigurationService
from app.domain.user.contracts import User
from app.domain.whatsapp_configuration.contracts import WhatsAppSecretRotation
from app.infrastructure.database import SessionLocal, engine
from app.infrastructure.repositories.audit_repository import SqlAlchemyAuditRepository
from app.infrastructure.repositories.bot_repository import BotRepository
from app.infrastructure.repositories.organization_repository import (
    OrganizationRepository,
)
from app.infrastructure.repositories.plan_repository import SqlAlchemyPlanRepository
from app.infrastructure.repositories.user_repository import UserRepository
from app.infrastructure.repositories.whatsapp_configuration_repository import (
    SqlAlchemyWhatsAppConfigurationRepository,
)
from app.infrastructure.settings import get_settings
from app.observability.context import correlation_context
from app.security.secret_cipher import EnvironmentSecretCipher
from sqlalchemy import text
from sqlalchemy.orm import Session

EXPECTED_HOST = os.environ.get("LURI_OPS_DB_HOST", "")
OWNER_EMAIL = os.environ.get("LURI_OPS_OWNER_EMAIL", "")
EXPECTED_SHA = "6163751304a261e9a1faf1ad10554951626dcfbe"
ORGANIZATION_ID = UUID("3678150b-2f35-40ab-ad8d-cb45afdeb839")
BOT_ID = UUID("2a070ecb-fc5f-46b2-8c9b-77f793726bc4")
OWNER_ID = UUID("1d7b6b45-3847-44fb-b107-6e5a83bbd37a")
CONFIGURATION_ID = UUID("0c20eba4-2ee9-4ed8-9fc8-107d612d3ce4")


def validate_target(
    session: Session,
    *,
    for_update: bool = False,
    allow_webhook_secrets: bool = False,
    allow_receiving_channel: bool = False,
) -> tuple[User, datetime, bool]:
    settings = get_settings()
    if (
        not EXPECTED_HOST
        or not OWNER_EMAIL
        or engine.url.host != EXPECTED_HOST
        or engine.url.database != "defaultdb"
        or engine.url.query.get("sslmode") != "require"
        or settings.build_sha != EXPECTED_SHA
        or settings.environment.value != "production"
        or settings.ai_enabled
        or settings.ai_pilot_scopes
        or settings.ai_openai_api_key
        or settings.public_bootstrap_enabled
        or settings.whatsapp_live_client_mode != "disabled"
    ):
        raise SystemExit("Wrong staging target or unsafe configuration; no changes")
    if (
        session.execute(text("SELECT version_num FROM alembic_version")).scalar_one()
        != "20260921_0026"
    ):
        raise SystemExit("Unexpected migration; no changes")
    organization = OrganizationRepository(session).get(ORGANIZATION_ID)
    owner = UserRepository(session).find_by_email(OWNER_EMAIL)
    bot = BotRepository(session).get(BOT_ID)
    if (
        organization is None
        or organization.slug != "kalivur"
        or organization.status != "active"
        or owner is None
        or owner.id != OWNER_ID
        or owner.organization_id != ORGANIZATION_ID
        or owner.role != "organization_owner"
        or owner.status != "active"
        or bot is None
        or bot.organization_id != ORGANIZATION_ID
        or bot.slug != "kalivur-marketing-pro"
        or bot.status != "inactive"
        or bot.settings.get("generative_ai") != {"enabled": False}
    ):
        raise SystemExit("Unexpected tenant, owner, or bot; no changes")
    channel = SqlAlchemyWhatsAppConfigurationRepository(session).get_scoped(
        CONFIGURATION_ID, ORGANIZATION_ID, BOT_ID, for_update=for_update
    )
    if (
        channel is None
        or channel.phone_number_id != "1354348231086256"
        or channel.whatsapp_business_account_id != "974780138964664"
        or (
            (channel.status, channel.webhook_enabled)
            not in (
                {("draft", False), ("inactive", False), ("active", True)}
                if allow_receiving_channel
                else {("draft", False)}
            )
        )
        or (
            not allow_webhook_secrets
            and (
                channel.verify_token_ciphertext is not None
                or channel.app_secret_ciphertext is not None
            )
        )
    ):
        raise SystemExit("Unexpected test channel state; no changes")
    return (
        User.model_validate(owner, from_attributes=True),
        channel.updated_at,
        channel.access_token_ciphertext is not None,
    )


def read_confirmed_token() -> str:
    if not sys.stdin.isatty() or not sys.stderr.isatty():
        raise SystemExit("Interactive terminal required; no credential was read")
    try:
        with warnings.catch_warnings():
            warnings.simplefilter("error", getpass.GetPassWarning)
            token = getpass.getpass("Access token de Meta (entrada oculta): ")
        if (
            not 20 <= len(token) <= 4000
            or not token.isascii()
            or not token.isprintable()
            or any(char.isspace() for char in token)
        ):
            raise SystemExit("Invalid token format; no changes")
        confirmation = input(
            "Solo canal de PRUEBA en STAGING, inactivo. "
            "Escribe GUARDAR para cifrar y guardar: "
        )
        if confirmation != "GUARDAR":
            raise SystemExit("Cancelled; no changes")
        return token
    except (EOFError, KeyboardInterrupt, getpass.GetPassWarning):
        raise SystemExit("Hidden input unavailable or cancelled; no changes") from None


def main() -> None:
    parser = argparse.ArgumentParser(description=__doc__)
    parser.add_argument("--apply", action="store_true")
    args = parser.parse_args()
    with SessionLocal() as session:
        _, original_updated_at, configured = validate_target(session)
    # The DB transaction is closed before the human enters any credential.
    if configured:
        print(json.dumps({"status": "access_token_already_configured_no_changes"}))
        return
    if not args.apply:
        print(
            json.dumps(
                {
                    "status": "ready_for_hidden_access_token_input",
                    "configuration_id": str(CONFIGURATION_ID),
                    "access_token_configured": False,
                    "channel_status": "draft",
                    "webhook_enabled": False,
                    "transport": "disabled",
                    "ai_enabled": False,
                }
            )
        )
        return

    token = read_confirmed_token()
    with SessionLocal() as session, correlation_context():
        actor, current_updated_at, configured = validate_target(
            session, for_update=True
        )
        if configured or current_updated_at != original_updated_at:
            raise SystemExit("Channel changed during input; no changes")
        result = WhatsAppConfigurationService(
            SqlAlchemyWhatsAppConfigurationRepository(session),
            BotRepository(session),
            OrganizationRepository(session),
            EnvironmentSecretCipher.from_settings(get_settings()),
            session,
            PlanEnforcementService(SqlAlchemyPlanRepository(session)),
            SqlAlchemyAuditRepository(session),
        ).rotate_secrets(
            ORGANIZATION_ID,
            BOT_ID,
            CONFIGURATION_ID,
            WhatsAppSecretRotation(access_token=token),
            actor,
        )
        print(
            json.dumps(
                {
                    "status": "test_access_token_saved_encrypted",
                    "configuration_id": str(result.id),
                    "access_token_configured": result.access_token_configured,
                    "channel_status": result.status,
                    "webhook_enabled": result.webhook_enabled,
                    "provider_validation": "not_performed",
                }
            )
        )


if __name__ == "__main__":
    try:
        main()
    except Exception:
        # Do not expose credential-bearing validation errors, SQL params or URLs.
        raise SystemExit(
            "Operation failed; no credential details printed. "
            "Run read-only mode to inspect configured status."
        ) from None
