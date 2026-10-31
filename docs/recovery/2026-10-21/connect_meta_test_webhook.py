"""Exact-target staging webhook operations. No WhatsApp sends or AI activation.

Default is a local preflight. --inspect-meta performs read-only Graph queries,
including a single GET debug_token subrequest carried in a POST batch body so
neither access token nor app secret appears in the actual HTTP request URL.
Never print request bodies, headers, provider bodies, credentials or exceptions.
"""

import argparse
import hashlib
import hmac
import json
import logging
import os
import re
import time
from dataclasses import dataclass
from datetime import UTC, datetime
from urllib.parse import urlencode

import httpx
from app.application.plans.service import PlanEnforcementService
from app.application.whatsapp_configuration.service import WhatsAppConfigurationService
from app.domain.whatsapp_configuration.contracts import (
    WhatsAppChannelConfigurationUpdate,
)
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
    engine,
    validate_target,
)
from sqlalchemy.orm import Session

APP_ID = "957426266669769"
SYSTEM_USER_ID = "61594229064395"
SCOPED_USER_ID = os.environ.get("LURI_OPS_SCOPED_USER_ID", "")
WABA_ID = "974780138964664"
PHONE_ID = "1354348231086256"
PUBLIC_ID = os.environ.get("LURI_OPS_PUBLIC_WEBHOOK_ID", "")
CALLBACK = f"https://staging-api.kalivur.com/webhooks/whatsapp/{PUBLIC_ID}"
SCOPES = ("whatsapp_business_management", "whatsapp_business_messaging")


@dataclass(repr=False, frozen=True)
class Snapshot:
    updated_at: datetime
    status: str
    webhook_enabled: bool
    access_ciphertext: str
    app_ciphertext: str
    verify_ciphertext: str


def snapshot() -> Snapshot:
    with SessionLocal() as session:
        _, updated_at, token_present = validate_target(
            session, allow_webhook_secrets=True, allow_receiving_channel=True
        )
        row = SqlAlchemyWhatsAppConfigurationRepository(session).get_scoped(
            CONFIGURATION_ID, ORGANIZATION_ID, BOT_ID
        )
        if (
            row is None
            or str(row.public_webhook_id) != PUBLIC_ID
            or not token_present
            or row.app_secret_ciphertext is None
            or row.verify_token_ciphertext is None
            or row.access_token_ciphertext is None
        ):
            raise SystemExit("Unexpected test channel or missing secrets; no changes")
        return Snapshot(
            updated_at,
            row.status,
            row.webhook_enabled,
            row.access_token_ciphertext,
            row.app_secret_ciphertext,
            row.verify_token_ciphertext,
        )


def graph_version() -> str:
    version = get_settings().whatsapp_api_version
    if re.fullmatch(r"v[0-9]+\.[0-9]+", version) is None:
        raise SystemExit("Invalid Graph version; no requests")
    return version


def credentials(state: Snapshot) -> tuple[str, str, str]:
    cipher = EnvironmentSecretCipher.from_settings(get_settings())
    token = cipher.decrypt(state.access_ciphertext)
    app_secret = cipher.decrypt(state.app_ciphertext)
    verify_token = cipher.decrypt(state.verify_ciphertext)
    if (
        not 20 <= len(token) <= 4000
        or not token.isascii()
        or not token.isprintable()
        or any(c.isspace() for c in token)
        or re.fullmatch(r"[0-9a-fA-F]{32}", app_secret) is None
        or re.fullmatch(r"[A-Za-z0-9_-]{32,128}", verify_token) is None
    ):
        raise SystemExit("Stored secret format invalid; no requests")
    return token, app_secret, verify_token


def new_client() -> httpx.Client:
    logging.disable(logging.CRITICAL)
    return httpx.Client(
        timeout=httpx.Timeout(15.0),
        follow_redirects=False,
        trust_env=False,
        transport=httpx.HTTPTransport(retries=0),
        headers={"User-Agent": "Mozilla/5.0 Luri staging readiness"},
    )


def safe_request(client: httpx.Client, method: str, url: str, **kwargs):
    try:
        response = client.request(method, url, **kwargs)
        if len(response.content) > 262_144:
            return None, {"result": "response_too_large"}
        if response.status_code != 200:
            result = {"result": "http_error", "http_status": response.status_code}
            try:
                error = response.json().get("error", {})
                if type(error.get("code")) is int:
                    result["provider_error_code"] = error["code"]
            except Exception:
                pass
            return None, result
        payload = response.json()
        if not isinstance(payload, (dict, list)):
            return None, {"result": "unexpected_response"}
        return payload, {"result": "ok"}
    except Exception:
        return None, {"result": "request_failed_no_details"}


def inspect_token(client, version, token, app_secret):
    # Only the encrypted HTTPS body contains the subject token. This batch has
    # exactly one read-only subrequest, authenticated by this specific app.
    batch = [
        {
            "method": "GET",
            "relative_url": "debug_token?" + urlencode({"input_token": token}),
        }
    ]
    payload, result = safe_request(
        client,
        "POST",
        f"https://graph.facebook.com/{version}/",
        headers={"Authorization": f"Bearer {APP_ID}|{app_secret}"},
        data={"batch": json.dumps(batch)},
    )
    if not isinstance(payload, list) or len(payload) != 1:
        return {"passed": False, "query": result}
    entry = payload[0]
    if not isinstance(entry, dict) or entry.get("code") != 200:
        return {"passed": False, "query": {"result": "batch_subrequest_failed"}}
    try:
        data = json.loads(entry["body"])["data"]
        expires_at = data.get("expires_at")
        valid_expiry = (
            type(expires_at) is int and 3600 < expires_at - time.time() <= 61 * 86400
        )
        granted = data.get("scopes", [])
        checks = {
            "valid": data.get("is_valid") is True,
            "app_id_matches": str(data.get("app_id")) == APP_ID,
            "system_user_type": data.get("type") == "SYSTEM_USER",
            "known_user_id_matches": str(data.get("user_id"))
            in {uid for uid in (SYSTEM_USER_ID, SCOPED_USER_ID) if uid},
            "limited_expiration_valid": valid_expiry,
            "required_scopes_present": isinstance(granted, list)
            and all(s in granted for s in SCOPES),
        }
        return {
            "passed": all(checks.values()),
            **checks,
            "expires_at_utc": (
                datetime.fromtimestamp(expires_at, UTC).isoformat()
                if valid_expiry
                else None
            ),
        }
    except Exception:
        return {"passed": False, "query": {"result": "invalid_debug_metadata"}}


def inspect_subscription(client, version, token):
    payload, result = safe_request(
        client,
        "GET",
        f"https://graph.facebook.com/{version}/{WABA_ID}/subscribed_apps",
        headers={"Authorization": f"Bearer {token}"},
    )
    if not isinstance(payload, dict) or not isinstance(payload.get("data"), list):
        return {"query": result, "known_state": False}
    matches = [
        row
        for row in payload["data"]
        if isinstance(row, dict)
        and isinstance(row.get("whatsapp_business_api_data"), dict)
        and str(row["whatsapp_business_api_data"].get("id")) == APP_ID
    ]
    if len(matches) > 1:
        return {"known_state": False, "query": {"result": "ambiguous_subscription"}}
    override = matches[0].get("override_callback_uri") if matches else None
    if override is not None and not isinstance(override, str):
        return {"known_state": False, "query": {"result": "unknown_override_format"}}
    return {
        "known_state": True,
        "app_subscribed": bool(matches),
        "override_present": bool(override),
        "override_matches_staging_test": override == CALLBACK,
        "safe_to_set_test_override": override in (None, "", CALLBACK),
        "query": result,
    }


def inspect_remote(state):
    version = graph_version()
    token, app_secret, _ = credentials(state)
    with new_client() as client:
        token_result = inspect_token(client, version, token, app_secret)
        if not token_result["passed"]:
            return {"token": token_result, "ready_to_connect": False}
        subscription = inspect_subscription(client, version, token)
        return {
            "token": token_result,
            "subscription": subscription,
            "ready_to_connect": subscription.get("safe_to_set_test_override", False),
        }


class AtomicServiceSession(Session):
    """Make both existing service commits flush until the outer final commit."""

    def commit(self) -> None:
        self.flush()


def set_receiving(expected: Snapshot, enabled: bool) -> Snapshot:
    with (
        AtomicServiceSession(bind=engine, autoflush=False) as session,
        correlation_context(),
    ):
        actor, updated_at, token_present = validate_target(
            session,
            for_update=True,
            allow_webhook_secrets=True,
            allow_receiving_channel=True,
        )
        row = SqlAlchemyWhatsAppConfigurationRepository(session).get_scoped(
            CONFIGURATION_ID, ORGANIZATION_ID, BOT_ID, for_update=True
        )
        if (
            row is None
            or str(row.public_webhook_id) != PUBLIC_ID
            or not token_present
            or updated_at != expected.updated_at
            or row.access_token_ciphertext != expected.access_ciphertext
            or row.app_secret_ciphertext != expected.app_ciphertext
            or row.verify_token_ciphertext != expected.verify_ciphertext
        ):
            raise SystemExit("Channel changed before transition; no changes")
        service = WhatsAppConfigurationService(
            SqlAlchemyWhatsAppConfigurationRepository(session),
            BotRepository(session),
            OrganizationRepository(session),
            EnvironmentSecretCipher.from_settings(get_settings()),
            session,
            PlanEnforcementService(SqlAlchemyPlanRepository(session)),
            SqlAlchemyAuditRepository(session),
        )
        if enabled:
            if row.status == "active" and row.webhook_enabled:
                return expected
            service.update(
                ORGANIZATION_ID,
                BOT_ID,
                CONFIGURATION_ID,
                WhatsAppChannelConfigurationUpdate(webhook_enabled=True),
                actor,
            )
            service.activate(ORGANIZATION_ID, BOT_ID, CONFIGURATION_ID, actor)
        else:
            if row.status == "inactive" and not row.webhook_enabled:
                return expected
            service.deactivate(ORGANIZATION_ID, BOT_ID, CONFIGURATION_ID, actor)
            service.update(
                ORGANIZATION_ID,
                BOT_ID,
                CONFIGURATION_ID,
                WhatsAppChannelConfigurationUpdate(webhook_enabled=False),
                actor,
            )
        Session.commit(session)
    return snapshot()


def public_security_checks(client, app_secret):
    body = b'{"purpose":"luri-staging-signature-check"}'
    signature = (
        "sha256=" + hmac.new(app_secret.encode(), body, hashlib.sha256).hexdigest()
    )
    url = CALLBACK + "/validate-signature"
    outcomes = {}
    for name, headers, expected_code in (
        ("valid_signature", {"X-Hub-Signature-256": signature}, 200),
        ("missing_signature_rejected", {}, 403),
        (
            "wrong_signature_rejected",
            {"X-Hub-Signature-256": "sha256=" + "0" * 64},
            403,
        ),
    ):
        try:
            response = client.post(url, content=body, headers=headers)
            outcomes[name] = response.status_code == expected_code and (
                name != "valid_signature" or response.text == "Signature valid"
            )
        except Exception:
            outcomes[name] = False
    try:
        response = client.get(
            CALLBACK,
            params={
                "hub.mode": "subscribe",
                "hub.verify_token": "intentionally-invalid-test-value",
                "hub.challenge": "luri-staging-negative-check",
            },
        )
        outcomes["wrong_verify_token_rejected"] = response.status_code == 403
    except Exception:
        outcomes["wrong_verify_token_rejected"] = False
    return outcomes


def subscribe_test_override(client, version, token, verify_token):
    payload, result = safe_request(
        client,
        "POST",
        f"https://graph.facebook.com/{version}/{WABA_ID}/subscribed_apps",
        headers={"Authorization": f"Bearer {token}"},
        json={"override_callback_uri": CALLBACK, "verify_token": verify_token},
        timeout=30.0,
    )
    return {
        "acknowledged": isinstance(payload, dict) and payload.get("success") is True,
        "query": result,
    }


def connect():
    before = snapshot()
    preflight = inspect_remote(before)
    if not preflight["ready_to_connect"]:
        return {
            "status": "connection_preflight_failed_no_changes",
            "preflight": preflight,
        }
    token, app_secret, verify_token = credentials(before)
    current = set_receiving(before, True)
    try:
        with new_client() as client:
            security = public_security_checks(client, app_secret)
            if not all(security.values()):
                set_receiving(current, False)
                return {
                    "status": "public_security_check_failed_local_disabled",
                    "checks": security,
                }
            already_connected = preflight["subscription"][
                "override_matches_staging_test"
            ]
            subscription_result = (
                {
                    "acknowledged": True,
                    "query": {"result": "already_configured_no_write"},
                }
                if already_connected
                else subscribe_test_override(
                    client, graph_version(), token, verify_token
                )
            )
            # One readback resolves an uncertain POST outcome; never retry the POST.
            final = inspect_subscription(client, graph_version(), token)
            if not final.get("override_matches_staging_test"):
                set_receiving(current, False)
                return {
                    "status": "subscription_not_confirmed_local_disabled",
                    "registration": subscription_result,
                    "subscription": final,
                    "remote_state_may_require_review": True,
                }
            final_state = snapshot()
            if final_state.status != "active" or not final_state.webhook_enabled:
                raise RuntimeError("Unexpected final local state")
            return {
                "status": "test_waba_webhook_connected",
                "checks": security,
                "registration": subscription_result,
                "subscription": final,
                "token": preflight["token"],
                "channel_status": "active",
                "webhook_enabled": True,
                "bot_status": "inactive",
                "transport": "disabled",
                "ai_enabled": False,
                "messages_sent": 0,
                "general_app_callback_changed": False,
            }
    except BaseException:
        try:
            set_receiving(snapshot(), False)
            rollback = "local_channel_disabled"
        except BaseException:
            rollback = "local_disable_requires_owner_review"
        return {
            "status": "connection_failed_no_credential_details",
            "rollback": rollback,
        }


def main():
    parser = argparse.ArgumentParser(description=__doc__)
    mode = parser.add_mutually_exclusive_group()
    mode.add_argument("--inspect-meta", action="store_true")
    mode.add_argument("--connect", action="store_true")
    mode.add_argument("--disable-local", action="store_true")
    args = parser.parse_args()
    if args.connect:
        print(json.dumps(connect()))
        return
    if args.disable_local:
        state = set_receiving(snapshot(), False)
        print(
            json.dumps(
                {
                    "status": "local_test_webhook_disabled",
                    "channel_status": state.status,
                    "webhook_enabled": state.webhook_enabled,
                    "meta_subscription_changed": False,
                }
            )
        )
        return
    state = snapshot()
    report = {
        "status": "test_webhook_preflight_passed",
        "configuration_id": str(CONFIGURATION_ID),
        "callback_url": CALLBACK,
        "channel_status": state.status,
        "webhook_enabled": state.webhook_enabled,
        "bot_status": "inactive",
        "transport": "disabled",
        "ai_enabled": False,
        "messages_sent": 0,
    }
    if args.inspect_meta:
        report["meta"] = inspect_remote(state)
    print(json.dumps(report))


if __name__ == "__main__":
    try:
        main()
    except Exception:
        raise SystemExit("Operation failed; no credential details printed") from None
