class PlanError(ValueError):
    safe_code = "PLAN_UNAVAILABLE"


class PlanNotFound(PlanError):
    safe_code = "PLAN_NOT_FOUND"


class PlanAssignmentNotFound(PlanError):
    safe_code = "PLAN_ASSIGNMENT_NOT_FOUND"


class PlanFeatureNotAvailable(PlanError):
    safe_code = "PLAN_FEATURE_NOT_AVAILABLE"


class PlanLimitReached(PlanError):
    safe_code = "PLAN_LIMIT_REACHED"

    def __init__(self, limit_key: str) -> None:
        self.limit_key = limit_key
        super().__init__(limit_key)


class PlanVersionConflict(PlanError):
    safe_code = "PLAN_VERSION_CONFLICT"


class PlanForbidden(PlanError):
    safe_code = "PLAN_FORBIDDEN"


class PlanUnavailable(PlanError):
    safe_code = "PLAN_UNAVAILABLE"
