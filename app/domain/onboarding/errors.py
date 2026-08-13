from app.domain.onboarding.contracts import BlockingReason


class OnboardingError(ValueError):
    safe_code = "ONBOARDING_UNAVAILABLE"


class OnboardingOrganizationNotFound(OnboardingError):
    safe_code = "ONBOARDING_ORGANIZATION_NOT_FOUND"


class OnboardingForbidden(OnboardingError):
    safe_code = "ONBOARDING_FORBIDDEN"


class OnboardingNotStarted(OnboardingError):
    safe_code = "ONBOARDING_NOT_STARTED"


class OnboardingNotReady(OnboardingError):
    safe_code = "ONBOARDING_NOT_READY"

    def __init__(self, blockers: tuple[BlockingReason, ...]) -> None:
        self.blockers = blockers
        super().__init__(self.safe_code)


class OnboardingVersionConflict(OnboardingError):
    safe_code = "ONBOARDING_VERSION_CONFLICT"


class OnboardingUnavailable(OnboardingError):
    safe_code = "ONBOARDING_UNAVAILABLE"


class OnboardingInvalidRequest(OnboardingError):
    safe_code = "ONBOARDING_INVALID_REQUEST"
