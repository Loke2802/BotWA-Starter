"""Prepare one draft Meta test channel in rebuilt staging; read-only by default.

No credentials, activation, subscriptions, network calls, or message sends.
The real Kalivur phone remains separate from this Meta test asset.
"""

import argparse
import json
import os
from uuid import UUID

from app.application.plans.service import PlanEnforcementService
from app.application.whatsapp_configuration.service import WhatsAppConfigurationService
from app.domain.user.contracts import User
from app.domain.whatsapp_configuration.contracts import (
    WhatsAppChannelConfigurationCreate,
)
from app.infrastructure.database import SessionLocal, engine
from app.infrastructure.models.whatsapp_channel_configuration import (
    WhatsAppChannelConfigurationModel,
)
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
from sqlalchemy import select, text

EXPECTED_HOST = os.environ.get("LURI_OPS_DB_HOST", "")
OWNER_EMAIL = os.environ.get("LURI_OPS_OWNER_EMAIL", "")
EXPECTED_SHA = "6163751304a261e9a1faf1ad10554951626dcfbe"
ORGANIZATION_ID = UUID("3678150b-2f35-40ab-ad8d-cb45afdeb839")
BOT_ID = UUID("2a070ecb-fc5f-46b2-8c9b-77f793726bc4")
OWNER_ID = UUID("1d7b6b45-3847-44fb-b107-6e5a83bbd37a")
PHONE_NUMBER_ID = "1354348231086256"
WABA_ID = "974780138964664"
DISPLAY_NAME = "Meta test - Luri review (+1 555-197-8260)"


def main() -> None:
    parser = argparse.ArgumentParser(description=__doc__)
    parser.add_argument("--apply", action="store_true")
    args = parser.parse_args()
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

    with SessionLocal() as session, correlation_context():
        if (
            session.execute(
                text("SELECT version_num FROM alembic_version")
            ).scalar_one()
            != "20260921_0026"
        ):
            raise SystemExit("Unexpected migration; no changes")
        organization_repository = OrganizationRepository(session)
        organization = organization_repository.get(ORGANIZATION_ID)
        owner = UserRepository(session).find_by_email(OWNER_EMAIL)
        bot_repository = BotRepository(session)
        bot = bot_repository.get(BOT_ID)
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

        existing = list(
            session.scalars(select(WhatsAppChannelConfigurationModel)).all()
        )
        if existing:
            channel = existing[0]
            if (
                len(existing) != 1
                or channel.organization_id != ORGANIZATION_ID
                or channel.bot_id != BOT_ID
                or channel.phone_number_id != PHONE_NUMBER_ID
                or channel.whatsapp_business_account_id != WABA_ID
                or channel.display_name != DISPLAY_NAME
                or channel.status != "draft"
                or channel.webhook_enabled
                or channel.verify_token_ciphertext is not None
                or channel.access_token_ciphertext is not None
                or channel.app_secret_ciphertext is not None
            ):
                raise SystemExit("Unexpected existing channels; no changes")
            print(
                json.dumps(
                    {
                        "status": "draft_test_channel_already_exists",
                        "configuration_id": str(channel.id),
                        "webhook_enabled": False,
                        "secrets_configured": False,
                    }
                )
            )
            return

        request = WhatsAppChannelConfigurationCreate(
            display_name=DISPLAY_NAME,
            phone_number_id=PHONE_NUMBER_ID,
            whatsapp_business_account_id=WABA_ID,
            webhook_enabled=False,
        )
        if not args.apply:
            print(json.dumps({"status": "ready_for_draft_test_channel_setup"}))
            return
        result = WhatsAppConfigurationService(
            SqlAlchemyWhatsAppConfigurationRepository(session),
            bot_repository,
            organization_repository,
            EnvironmentSecretCipher.from_settings(settings),
            session,
            PlanEnforcementService(SqlAlchemyPlanRepository(session)),
            SqlAlchemyAuditRepository(session),
        ).create(
            ORGANIZATION_ID,
            BOT_ID,
            request,
            User.model_validate(owner, from_attributes=True),
        )
        print(
            json.dumps(
                {
                    "status": "draft_test_channel_created",
                    "configuration_id": str(result.id),
                    "organization_id": str(result.organization_id),
                    "bot_id": str(result.bot_id),
                    "channel_status": result.status,
                    "webhook_enabled": result.webhook_enabled,
                    "secrets_configured": any(
                        (
                            result.verify_token_configured,
                            result.access_token_configured,
                            result.app_secret_configured,
                        )
                    ),
                }
            )
        )


if __name__ == "__main__":
    main()
