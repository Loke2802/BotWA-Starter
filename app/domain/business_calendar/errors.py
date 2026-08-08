class BusinessCalendarError(ValueError):
    safe_code = "BUSINESS_CALENDAR_ERROR"


class BusinessCalendarNotFound(BusinessCalendarError):
    safe_code = "BUSINESS_CALENDAR_NOT_FOUND"


class BusinessCalendarForbidden(BusinessCalendarError):
    safe_code = "BUSINESS_CALENDAR_FORBIDDEN"


class BusinessCalendarConflict(BusinessCalendarError):
    safe_code = "BUSINESS_CALENDAR_CONFLICT"


class BusinessCalendarInactive(BusinessCalendarConflict):
    safe_code = "BUSINESS_CALENDAR_INACTIVE"


class ScheduleValidationError(BusinessCalendarError):
    safe_code = "SCHEDULE_VALIDATION_ERROR"


class ScheduleVersionConflict(BusinessCalendarConflict):
    safe_code = "SCHEDULE_VERSION_CONFLICT"


class TimezoneInvalid(ScheduleValidationError):
    safe_code = "TIMEZONE_INVALID"


class LocalTimeNonexistent(ScheduleValidationError):
    safe_code = "LOCAL_TIME_NONEXISTENT"


class LocalTimeAmbiguous(ScheduleValidationError):
    safe_code = "LOCAL_TIME_AMBIGUOUS"


class IdempotencyConflict(BusinessCalendarConflict):
    safe_code = "IDEMPOTENCY_CONFLICT"


class ExternalCalendarUnavailable(BusinessCalendarError):
    safe_code = "EXTERNAL_CALENDAR_UNAVAILABLE"


class BusinessCalendarPersistenceError(BusinessCalendarError):
    safe_code = "BUSINESS_CALENDAR_PERSISTENCE_ERROR"
