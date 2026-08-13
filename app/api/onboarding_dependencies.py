from collections.abc import Generator

from app.application.onboarding.metrics import onboarding_metrics
from app.application.onboarding.readiness import OnboardingReadinessService
from app.application.onboarding.service import OnboardingService
from app.infrastructure.database import get_session
from app.infrastructure.repositories.audit_repository import SqlAlchemyAuditRepository
from app.infrastructure.repositories.onboarding_repository import (
    SqlAlchemyOnboardingRepository,
)


def get_onboarding_service() -> Generator[OnboardingService]:
    session_generator = get_session()
    session = next(session_generator)
    try:
        repository = SqlAlchemyOnboardingRepository(session)
        readiness = OnboardingReadinessService(repository, metrics=onboarding_metrics)
        yield OnboardingService(
            repository,
            readiness,
            session,
            SqlAlchemyAuditRepository(session),
            metrics=onboarding_metrics,
        )
    finally:
        session_generator.close()
