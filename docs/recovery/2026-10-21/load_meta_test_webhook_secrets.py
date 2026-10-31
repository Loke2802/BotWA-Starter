"""Load existing Luri App Secret and human-chosen verify token into staging.

Read-only by default. Human completes hidden input and GUARDAR in --apply mode.
No generation, rotation or readback of Meta credentials; no activation or HTTP.
"""

import argparse
import getpass
import hmac
import json
import re
import sys
import warnings
from datetime import datetime

from app.application.plans.service import PlanEnforcementService
from app.application.whatsapp_configuration.service import WhatsAppConfigurationService
from app.domain.user.contracts import User
from app.domain.whatsapp_configuration.contracts import WhatsAppSecretRotation
from app.infrastructure.repositories.audit_repository import SqlAlchemyAuditRepository
from app.infrastructure.repositories.bot_repository import BotRepository
from app.infrastructure.repositories.organization_repository import (
    OrganizationRepository,
)
from app.infrastructure.repositories.plan_repository import SqlAlchemyPlanRepository
from app.infrastructure.repositories.whatsapp_configuration_repository import (
    SqlAlchemyWhatsAppConfigurationRepository,
)
from app.infrastructure.settings import get_settings
from app.observability.context import correlation_context
from app.security.secret_cipher import EnvironmentSecretCipher
from load_meta_test_access_token import (
    BOT_ID,
    CONFIGURATION_ID,
    ORGANIZATION_ID,
    SessionLocal,
    validate_target,
)
from sqlalchemy.orm import Session


def inspect_target(
    session: Session, *, for_update: bool = False
) -> tuple[User, datetime, bool, bool]:
    actor, updated_at, token_configured = validate_target(
        session, for_update=for_update, allow_webhook_secrets=True
    )
    if not token_configured:
        raise SystemExit("Access token must already be configured; no changes")
    channel = SqlAlchemyWhatsAppConfigurationRepository(session).get_scoped(
        CONFIGURATION_ID, ORGANIZATION_ID, BOT_ID, for_update=for_update
    )
    if channel is None:
        raise SystemExit("Test channel unavailable; no changes")
    return (
        actor,
        updated_at,
        channel.app_secret_ciphertext is not None,
        channel.verify_token_ciphertext is not None,
    )


def read_confirmed_secrets() -> tuple[str, str]:
    if not sys.stdin.isatty() or not sys.stderr.isatty():
        raise SystemExit("Interactive terminal required; no credential was read")
    try:
        with warnings.catch_warnings():
            warnings.simplefilter("error", getpass.GetPassWarning)
            app_secret = getpass.getpass(
                "App Secret EXISTENTE de Luri (entrada oculta): "
            )
            if re.fullmatch(r"[0-9a-fA-F]{32}", app_secret) is None:
                raise SystemExit("Invalid App Secret format; no changes")
            verify_token = getpass.getpass(
                "Verify token propio, 32-128 letras/numeros/_/- (entrada oculta): "
            )
            if re.fullmatch(r"[A-Za-z0-9_-]{32,128}", verify_token) is None:
                raise SystemExit("Invalid verify token format; no changes")
            confirmation_token = getpass.getpass(
                "Repite el verify token (entrada oculta): "
            )
            if not hmac.compare_digest(verify_token, confirmation_token):
                raise SystemExit("Verify token confirmation mismatch; no changes")
        confirmation = input(
            "Solo canal de PRUEBA en STAGING, sin activar. "
            "Escribe GUARDAR para cifrar ambos secretos: "
        )
        if confirmation != "GUARDAR":
            raise SystemExit("Cancelled; no changes")
        return app_secret, verify_token
    except (EOFError, KeyboardInterrupt, getpass.GetPassWarning):
        raise SystemExit("Hidden input unavailable or cancelled; no changes") from None


def main() -> None:
    parser = argparse.ArgumentParser(description=__doc__)
    parser.add_argument("--apply", action="store_true")
    args = parser.parse_args()
    with SessionLocal() as session:
        _, original_updated_at, app_configured, verify_configured = inspect_target(
            session
        )
    if app_configured or verify_configured:
        print(
            json.dumps(
                {
                    "status": "webhook_secrets_present_no_changes",
                    "app_secret_configured": app_configured,
                    "verify_token_configured": verify_configured,
                    "channel_status": "draft",
                    "webhook_enabled": False,
                    "transport": "disabled",
                    "ai_enabled": False,
                }
            )
        )
        return
    if not args.apply:
        print(
            json.dumps(
                {
                    "status": "ready_for_hidden_webhook_secrets_input",
                    "configuration_id": str(CONFIGURATION_ID),
                    "app_secret_configured": False,
                    "verify_token_configured": False,
                    "access_token_configured": True,
                    "channel_status": "draft",
                    "webhook_enabled": False,
                    "transport": "disabled",
                    "ai_enabled": False,
                }
            )
        )
        return

    # No DB session or transaction remains open during human entry.
    app_secret, verify_token = read_confirmed_secrets()
    with SessionLocal() as session, correlation_context():
        actor, current_updated_at, app_configured, verify_configured = inspect_target(
            session, for_update=True
        )
        if (
            app_configured
            or verify_configured
            or current_updated_at != original_updated_at
        ):
            raise SystemExit("Channel changed during input; no changes")
        result = WhatsAppConfigurationService(
            SqlAlchemyWhatsAppConfigurationRepository(session),
            BotRepository(session),
            OrganizationRepository(session),
            EnvironmentSecretCipher.from_settings(get_settings()),
            session,
            PlanEnforcementService(SqlAlchemyPlanRepository(session)),
            SqlAlchemyAuditRepository(session),
        ).rotate_secrets(
            ORGANIZATION_ID,
            BOT_ID,
            CONFIGURATION_ID,
            WhatsAppSecretRotation(app_secret=app_secret, verify_token=verify_token),
            actor,
        )
        print(
            json.dumps(
                {
                    "status": "test_webhook_secrets_saved_encrypted",
                    "configuration_id": str(result.id),
                    "access_token_configured": result.access_token_configured,
                    "app_secret_configured": result.app_secret_configured,
                    "verify_token_configured": result.verify_token_configured,
                    "channel_status": result.status,
                    "webhook_enabled": result.webhook_enabled,
                    "provider_validation": "not_performed",
                }
            )
        )


if __name__ == "__main__":
    try:
        main()
    except Exception:
        raise SystemExit("Operation failed; no credential details printed") from None
