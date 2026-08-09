class AnalyticsError(ValueError):
    safe_code = "ANALYTICS_UNAVAILABLE"


class AnalyticsInvalidRange(AnalyticsError):
    safe_code = "ANALYTICS_INVALID_RANGE"


class AnalyticsRangeTooLarge(AnalyticsError):
    safe_code = "ANALYTICS_RANGE_TOO_LARGE"


class AnalyticsInvalidGrouping(AnalyticsError):
    safe_code = "ANALYTICS_INVALID_GROUPING"


class AnalyticsDataIncomplete(AnalyticsError):
    safe_code = "ANALYTICS_DATA_INCOMPLETE"


class AnalyticsNotFound(AnalyticsError):
    safe_code = "ANALYTICS_NOT_FOUND"


class AnalyticsForbidden(AnalyticsError):
    safe_code = "ANALYTICS_FORBIDDEN"


class AnalyticsUnavailable(AnalyticsError):
    safe_code = "ANALYTICS_UNAVAILABLE"


class AnalyticsPersistenceError(AnalyticsUnavailable):
    pass
