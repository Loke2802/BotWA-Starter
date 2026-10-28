from collections.abc import Callable
from typing import Annotated

from fastapi import Depends
from sqlalchemy.orm import Session

from app.api.human_handoff_dependencies import get_human_handoff_service
from app.api.whatsapp_configuration_dependencies import get_whatsapp_secret_cipher
from app.application.human_handoff.service import HumanHandoffService
from app.application.plans.service import PlanEnforcementService
from app.application.webchat.service import WebchatService
from app.infrastructure.database import get_session
from app.infrastructure.repositories.plan_repository import SqlAlchemyPlanRepository
from app.infrastructure.settings import Settings, get_settings
from app.security.secret_cipher import SecretCipher


def get_webchat_service(
    session: Annotated[Session, Depends(get_session)],
    settings: Annotated[Settings, Depends(get_settings)],
    cipher: Annotated[SecretCipher, Depends(get_whatsapp_secret_cipher)],
    handoff: Annotated[HumanHandoffService, Depends(get_human_handoff_service)],
) -> WebchatService:
    return WebchatService(
        session,
        settings,
        cipher,
        handoff,
        PlanEnforcementService(SqlAlchemyPlanRepository(session)),
    )


def get_webchat_service_factory(
    session: Annotated[Session, Depends(get_session)],
    settings: Annotated[Settings, Depends(get_settings)],
    handoff: Annotated[HumanHandoffService, Depends(get_human_handoff_service)],
) -> Callable[[], WebchatService]:
    # Resolve encryption only if the selected conversation is a web session.
    # Adding this channel must not impose new dependencies on WhatsApp replies.
    return lambda: WebchatService(
        session,
        settings,
        get_whatsapp_secret_cipher(),
        handoff,
        PlanEnforcementService(SqlAlchemyPlanRepository(session)),
    )
