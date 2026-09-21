import hashlib
from uuid import UUID

from pydantic import ValidationError
from sqlalchemy.orm import Session

from app.domain.generative_ai.contracts import AIConfig
from app.infrastructure.models.bot import BotModel
from app.infrastructure.models.organization import OrganizationModel
from app.infrastructure.settings import Settings


def configuration(
    session: Session, settings: Settings, organization_id: UUID, bot_id: UUID
) -> AIConfig | None:
    if not settings.ai_enabled or (
        f"{organization_id}:{bot_id}" not in settings.ai_pilot_scopes
    ):
        return None
    bot = session.get(BotModel, bot_id)
    org = session.get(OrganizationModel, organization_id)
    if (
        bot is None
        or org is None
        or bot.organization_id != organization_id
        or bot.status != "active"
        or org.status != "active"
    ):
        return None
    try:
        config = AIConfig.model_validate((bot.settings or {}).get("generative_ai", {}))
    except ValidationError:
        return None
    return config if config.enabled else None


def config_hash(config: AIConfig) -> str:
    return hashlib.sha256(config.model_dump_json().encode()).hexdigest()
