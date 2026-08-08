class DashboardError(ValueError):
    safe_code = "DASHBOARD_UNAVAILABLE"


class DashboardInvalidRange(DashboardError):
    safe_code = "DASHBOARD_INVALID_RANGE"


class DashboardRangeTooLarge(DashboardInvalidRange):
    safe_code = "DASHBOARD_RANGE_TOO_LARGE"


class DashboardInvalidFilter(DashboardError):
    safe_code = "DASHBOARD_INVALID_FILTER"


class DashboardNotFound(DashboardError):
    safe_code = "DASHBOARD_NOT_FOUND"


class DashboardForbidden(DashboardError):
    safe_code = "DASHBOARD_FORBIDDEN"


class DashboardUnavailable(DashboardError):
    safe_code = "DASHBOARD_UNAVAILABLE"


class DashboardPersistenceError(DashboardUnavailable):
    pass
