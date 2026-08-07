from collections.abc import Generator

from app.application.automation_management.service import ManagedAutomationService
from app.application.human_handoff.service import HumanHandoffService
from app.infrastructure.database import get_session
from app.infrastructure.repositories.human_handoff_repository import (
    HumanHandoffRepository,
)
from app.infrastructure.repositories.managed_automation_repository import (
    ManagedAutomationRepository,
)


def get_managed_automation_service() -> Generator[ManagedAutomationService]:
    session_generator = get_session()
    session = next(session_generator)
    try:
        yield ManagedAutomationService(
            ManagedAutomationRepository(session),
            session,
            HumanHandoffService(HumanHandoffRepository(session), session),
        )
    finally:
        session_generator.close()
