class AuditError(ValueError):
    safe_code = "AUDIT_UNAVAILABLE"


class AuditInvalidRange(AuditError):
    safe_code = "AUDIT_INVALID_RANGE"


class AuditRangeTooLarge(AuditError):
    safe_code = "AUDIT_RANGE_TOO_LARGE"


class AuditInvalidCursor(AuditError):
    safe_code = "AUDIT_INVALID_CURSOR"


class AuditInvalidFilter(AuditError):
    safe_code = "AUDIT_INVALID_FILTER"


class AuditForbidden(AuditError):
    safe_code = "AUDIT_FORBIDDEN"


class AuditUnavailable(AuditError):
    safe_code = "AUDIT_UNAVAILABLE"


class AuditWriteError(AuditUnavailable):
    pass
