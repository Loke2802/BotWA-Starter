"""Prepare one inactive Kalivur pilot bot; default mode is read-only.

Uses the existing scoped BotService and audit writer. Does not activate a bot,
configure WhatsApp, publish knowledge, or invoke an AI provider.
"""

import argparse
import json
import os
from uuid import UUID

from app.application.bots.service import BotService
from app.application.plans.service import PlanEnforcementService
from app.domain.bot.contracts import BotCreate
from app.domain.user.contracts import User
from app.infrastructure.database import SessionLocal, engine
from app.infrastructure.repositories.audit_repository import SqlAlchemyAuditRepository
from app.infrastructure.repositories.bot_repository import BotRepository
from app.infrastructure.repositories.organization_repository import (
    OrganizationRepository,
)
from app.infrastructure.repositories.plan_repository import SqlAlchemyPlanRepository
from app.infrastructure.repositories.user_repository import UserRepository
from app.infrastructure.settings import get_settings
from app.observability.context import correlation_context
from sqlalchemy import text

EXPECTED_HOST = os.environ.get("LURI_OPS_DB_HOST", "")
EXPECTED_SHA = "6163751304a261e9a1faf1ad10554951626dcfbe"
ORGANIZATION_ID = UUID("3678150b-2f35-40ab-ad8d-cb45afdeb839")
OWNER_ID = UUID("1d7b6b45-3847-44fb-b107-6e5a83bbd37a")
OWNER_EMAIL = os.environ.get("LURI_OPS_OWNER_EMAIL", "")
BOT_SLUG = "kalivur-marketing-pro"


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
        if (
            organization is None
            or organization.slug != "kalivur"
            or organization.status != "active"
            or owner is None
            or owner.id != OWNER_ID
            or owner.organization_id != ORGANIZATION_ID
            or owner.role != "organization_owner"
            or owner.status != "active"
        ):
            raise SystemExit("Unexpected tenant or owner; no changes")
        repository = BotRepository(session)
        bots = repository.list_by_organization(ORGANIZATION_ID)
        if bots:
            if (
                len(bots) != 1
                or bots[0].slug != BOT_SLUG
                or bots[0].status != "inactive"
                or bots[0].settings.get("generative_ai") != {"enabled": False}
            ):
                raise SystemExit("Unexpected existing bots; no changes")
            print(
                json.dumps(
                    {"status": "inactive_bot_already_exists", "bot_id": str(bots[0].id)}
                )
            )
            return
        request = BotCreate(
            organization_id=ORGANIZATION_ID,
            name="Kalivur Marketing Pro",
            slug=BOT_SLUG,
            default_language="es",
            timezone="America/Lima",
            settings={"generative_ai": {"enabled": False}},
        )
        if not args.apply:
            print(json.dumps({"status": "ready_for_inactive_bot_setup"}))
            return
        bot = BotService(
            repository,
            organization_repository,
            session,
            SqlAlchemyAuditRepository(session),
            PlanEnforcementService(SqlAlchemyPlanRepository(session)),
        ).create(request, User.model_validate(owner, from_attributes=True))
        print(
            json.dumps(
                {
                    "status": "inactive_bot_created",
                    "bot_id": str(bot.id),
                    "organization_id": str(bot.organization_id),
                    "name": bot.name,
                    "bot_status": bot.status,
                    "ai_enabled": False,
                }
            )
        )


if __name__ == "__main__":
    main()
