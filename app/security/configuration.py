from urllib.parse import urlsplit

import structlog
from cryptography.fernet import Fernet

from app.infrastructure.settings import Environment, Settings

logger = structlog.get_logger(__name__)

_KNOWN_AUTH_SECRETS = frozenset(
    {
        "",
        "secret",
        "changeme",
        "local-development-secret-change-me",
    }
)


class SecurityConfigurationError(RuntimeError):
    """Raised when the selected deployment profile is unsafe."""


class SecurityConfigurationValidator:
    def validate(self, settings: Settings) -> None:
        if settings.environment != Environment.PRODUCTION:
            return

        failures: list[str] = []
        if settings.build_sha is None:
            failures.append("build_sha")
        if not self._is_strong_secret(settings.auth_secret_key):
            failures.append("auth_signing_key")
        if settings.auth_algorithm != "HS256":
            failures.append("auth_algorithm")
        if settings.legacy_core_api_enabled:
            failures.append("legacy_core_api")
        if settings.legacy_whatsapp_enabled:
            failures.append("legacy_whatsapp")
        if settings.public_bootstrap_enabled:
            failures.append("public_bootstrap")
        if not settings.allowed_hosts or "*" in settings.allowed_hosts:
            failures.append("allowed_hosts")
        if settings.cors_allow_credentials and "*" in settings.cors_origins:
            failures.append("cors")
        if len(settings.rate_limit_hmac_key) < 32:
            failures.append("rate_limit_hmac_key")
        if len(settings.audit_cursor_signing_key) < 32:
            failures.append("audit_cursor_signing_key")
        if settings.metrics_enabled:
            metrics_token = (
                settings.metrics_bearer_token.get_secret_value()
                if settings.metrics_bearer_token is not None
                else ""
            )
            reused_secrets = {
                settings.auth_secret_key,
                settings.rate_limit_hmac_key,
                settings.audit_cursor_signing_key,
                settings.integration_oauth_state_secret,
            }
            if (
                not self._is_strong_secret(metrics_token)
                or metrics_token in reused_secrets
            ):
                failures.append("metrics_bearer_token")
        if len(settings.integration_oauth_state_secret) < 32:
            failures.append("oauth_state_signing_key")
        if len(settings.contact_identity_hmac_key) < 32:
            failures.append("contact_identity_hmac_key")
        if not self._is_fernet_key(settings.whatsapp_secret_encryption_key):
            failures.append("whatsapp_encryption_key")
        if settings.whatsapp_live_client_mode == "fake":
            failures.append("fake_whatsapp_provider")
        if settings.billing_enabled:
            if not settings.billing_mercado_pago_access_token:
                failures.append("billing_access_token")
            if not settings.billing_mercado_pago_webhook_secret:
                failures.append("billing_webhook_secret")
            if not self._is_https_url(settings.billing_success_url):
                failures.append("billing_success_url")
            if not self._is_https_url(settings.billing_cancel_url):
                failures.append("billing_cancel_url")
        google_values = (
            settings.google_oauth_client_id,
            settings.google_oauth_client_secret,
            settings.google_oauth_redirect_uri,
        )
        if any(google_values) and (
            not all(google_values)
            or not self._is_https_url(settings.google_oauth_redirect_uri)
        ):
            failures.append("google_oauth_configuration")
        if any(google_values) and not self._is_fernet_key(
            settings.integration_secret_encryption_key
        ):
            failures.append("integration_encryption_key")

        if failures:
            logger.error(
                "production_security_validation_failed",
                failed_controls=tuple(sorted(set(failures))),
            )
            raise SecurityConfigurationError(
                "production security configuration is invalid: "
                + ", ".join(sorted(set(failures)))
            )

    @staticmethod
    def _is_https_url(value: str) -> bool:
        parsed = urlsplit(value)
        return parsed.scheme == "https" and bool(parsed.netloc) and not parsed.username

    @staticmethod
    def _is_strong_secret(value: str) -> bool:
        normalized = value.strip()
        return (
            normalized.lower() not in _KNOWN_AUTH_SECRETS
            and len(normalized) >= 32
            and len(set(normalized)) >= 8
        )

    @staticmethod
    def _is_fernet_key(value: str) -> bool:
        try:
            Fernet(value.encode("ascii"))
        except (TypeError, ValueError):
            return False
        return True
