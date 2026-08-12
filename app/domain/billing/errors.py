class BillingError(RuntimeError):
    safe_code = "BILLING_UNAVAILABLE"


class BillingDisabled(BillingError):
    safe_code = "BILLING_DISABLED"


class BillingNotConfigured(BillingError):
    safe_code = "NOT_CONFIGURED"


class BillingAccountNotFound(BillingError):
    safe_code = "ACCOUNT_NOT_FOUND"


class BillingPriceNotFound(BillingError):
    safe_code = "PRICE_NOT_FOUND"


class BillingPriceUnavailable(BillingError):
    safe_code = "PRICE_UNAVAILABLE"


class SubscriptionNotFound(BillingError):
    safe_code = "SUBSCRIPTION_NOT_FOUND"


class SubscriptionConflict(BillingError):
    safe_code = "SUBSCRIPTION_CONFLICT"


class InvalidBillingTransition(BillingError):
    safe_code = "INVALID_TRANSITION"


class BillingVersionConflict(BillingError):
    safe_code = "VERSION_CONFLICT"


class BillingProviderUnavailable(BillingError):
    safe_code = "PROVIDER_UNAVAILABLE"


class BillingProviderRejected(BillingError):
    safe_code = "PROVIDER_REJECTED"


class BillingWebhookInvalid(BillingError):
    safe_code = "WEBHOOK_INVALID"


class BillingEventDuplicate(BillingError):
    safe_code = "EVENT_DUPLICATE"


class BillingFallbackNotConfigured(BillingError):
    safe_code = "FALLBACK_NOT_CONFIGURED"


class BillingForbidden(BillingError):
    safe_code = "FORBIDDEN"
