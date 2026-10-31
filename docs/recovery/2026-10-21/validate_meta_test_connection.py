"""Read-only checks for the exact staging test channel; never send messages.

Default: local preflight only. --validate-meta: at most four bounded GET requests to
Meta, using the encrypted channel token in memory and in Authorization only.
No plaintext credentials, provider bodies, request URLs or exceptions are printed.
"""

import argparse
import json
import logging
import re

import httpx
from app.infrastructure.repositories.whatsapp_configuration_repository import (
    SqlAlchemyWhatsAppConfigurationRepository,
)
from app.infrastructure.settings import get_settings
from app.security.secret_cipher import EnvironmentSecretCipher
from load_meta_test_access_token import (
    BOT_ID,
    CONFIGURATION_ID,
    ORGANIZATION_ID,
    SessionLocal,
    validate_target,
)

EXPECTED_USER = "61594229064395"
EXPECTED_PHONE = "1354348231086256"
EXPECTED_WABA = "974780138964664"
EXPECTED_DISPLAY = "15551978260"
REQUIRED_SCOPES = (
    "whatsapp_business_management",
    "whatsapp_business_messaging",
)


def read_target() -> tuple[str, str, str]:
    with SessionLocal() as session:
        _, _, configured = validate_target(session)
        if not configured:
            raise SystemExit("Test channel token is not configured; no requests")
        channel = SqlAlchemyWhatsAppConfigurationRepository(session).get_scoped(
            CONFIGURATION_ID, ORGANIZATION_ID, BOT_ID
        )
        if channel is None or channel.access_token_ciphertext is None:
            raise SystemExit("Test channel unavailable; no requests")
        ciphertext = channel.access_token_ciphertext
        public_id = str(channel.public_webhook_id)
    # The transaction is closed before decryption or any remote request.
    version = get_settings().whatsapp_api_version
    if re.fullmatch(r"v[0-9]+\.[0-9]+", version) is None:
        raise SystemExit("Invalid Graph API version; no requests")
    return ciphertext, public_id, version


def safe_get(
    client: httpx.Client, path: str, params: dict[str, str]
) -> tuple[dict[str, object] | None, dict[str, object]]:
    try:
        response = client.get(path, params=params)
        if len(response.content) > 262_144:
            return None, {"result": "response_too_large"}
        if response.status_code != 200:
            return None, {
                "result": "http_error",
                "http_status": response.status_code,
            }
        payload = response.json()
        if not isinstance(payload, dict) or "error" in payload:
            return None, {"result": "unexpected_response"}
        return payload, {"result": "ok"}
    except Exception:
        return None, {"result": "request_failed_no_details"}


def validate_with_meta(
    ciphertext: str,
    version: str,
    *,
    identity_only: bool = False,
    access_only: bool = False,
) -> dict[str, object]:
    if identity_only and access_only:
        raise SystemExit("Choose one read-only validation mode; no requests")
    token = EnvironmentSecretCipher.from_settings(get_settings()).decrypt(ciphertext)
    if (
        not 20 <= len(token) <= 4000
        or not token.isascii()
        or not token.isprintable()
        or any(char.isspace() for char in token)
    ):
        raise SystemExit("Stored token format invalid; no requests")
    # Do not enable HTTP debug logging: headers contain the credential.
    logging.disable(logging.CRITICAL)
    with httpx.Client(
        base_url=f"https://graph.facebook.com/{version}/",
        headers={"Authorization": f"Bearer {token}"},
        timeout=httpx.Timeout(10.0),
        follow_redirects=False,
        trust_env=False,
        transport=httpx.HTTPTransport(retries=0),
    ) as client:
        identity, identity_result = (
            (None, {"result": "not_requested"})
            if access_only
            else safe_get(client, "me", {"fields": "id,name"})
        )
        identity_match = identity is not None and identity.get("id") == EXPECTED_USER
        node_result: dict[str, object] = {"result": "not_requested"}
        if (
            not identity_match
            and identity is not None
            and identity.get("name") == "kalivur_staging_bot"
        ):
            system_node, node_result = safe_get(
                client, EXPECTED_USER, {"fields": "id,name,system_user_id"}
            )
            if system_node is not None:
                node_ids = {
                    str(system_node.get("id")),
                    str(system_node.get("system_user_id")),
                }
                identity_match = (
                    EXPECTED_USER in node_ids
                    and str(identity.get("id")) in node_ids
                    and system_node.get("name") == "kalivur_staging_bot"
                )
        if not identity_match and not access_only:
            observed_id = identity.get("id") if identity is not None else None
            safe_id = (
                observed_id
                if isinstance(observed_id, str)
                and re.fullmatch(r"[0-9]{1,30}", observed_id)
                else None
            )
            return {
                "status": "identity_not_confirmed_no_further_requests",
                "identity": identity_result,
                "system_node_query": node_result,
                "expected_system_user_matches": False,
                "observed_user_id": safe_id,
                "expected_system_user_name_matches": (
                    identity is not None
                    and identity.get("name") == "kalivur_staging_bot"
                ),
            }
        if identity_only:
            return {
                "status": "meta_system_user_identity_confirmed",
                "expected_system_user_matches": True,
                "messages_sent": 0,
                "mutations": 0,
            }
        permissions, permissions_result = safe_get(client, "me/permissions", {})
        granted: set[str] = set()
        if permissions is not None and isinstance(permissions.get("data"), list):
            granted = {
                item["permission"]
                for item in permissions["data"]
                if isinstance(item, dict)
                and item.get("status") == "granted"
                and isinstance(item.get("permission"), str)
            }
        phones, phones_result = safe_get(
            client,
            f"{EXPECTED_WABA}/phone_numbers",
            {"fields": "id,display_phone_number", "limit": "25"},
        )
        matching = []
        if phones is not None and isinstance(phones.get("data"), list):
            matching = [
                item
                for item in phones["data"]
                if isinstance(item, dict) and item.get("id") == EXPECTED_PHONE
            ]
        phone_match = len(matching) == 1
        display_match = phone_match and (
            re.sub(r"\D", "", str(matching[0].get("display_phone_number", "")))
            == EXPECTED_DISPLAY
        )
        scope_results = {scope: scope in granted for scope in REQUIRED_SCOPES}
        checks_pass = all(scope_results.values()) and phone_match and display_match
        return {
            "status": (
                (
                    "meta_read_access_passed_identity_mapping_pending"
                    if access_only
                    else "meta_read_only_checks_passed"
                )
                if checks_pass
                else "meta_read_only_checks_incomplete"
            ),
            "expected_system_user_matches": None if access_only else True,
            "permissions_query": permissions_result,
            "required_scopes_granted": scope_results,
            "test_waba_phone_query": phones_result,
            "expected_phone_in_test_waba": phone_match,
            "test_display_phone_matches": display_match,
            "app_id_validation": "not_performed",
            "expiration_validation": "not_performed",
            "messages_sent": 0,
            "mutations": 0,
        }


def main() -> None:
    parser = argparse.ArgumentParser(description=__doc__)
    mode = parser.add_mutually_exclusive_group()
    mode.add_argument("--validate-meta", action="store_true")
    mode.add_argument("--identity-only", action="store_true")
    mode.add_argument("--access-only", action="store_true")
    args = parser.parse_args()
    ciphertext, public_id, version = read_target()
    report: dict[str, object] = {
        "status": "staging_test_connection_preflight_passed",
        "configuration_id": str(CONFIGURATION_ID),
        "callback_url": (
            f"https://staging-api.kalivur.com/webhooks/whatsapp/{public_id}"
        ),
        "graph_api_version": version,
        "channel_status": "draft",
        "webhook_enabled": False,
        "transport": "disabled",
        "ai_enabled": False,
        "app_secret_configured": False,
        "verify_token_configured": False,
    }
    if args.identity_only or args.validate_meta or args.access_only:
        report["meta"] = validate_with_meta(
            ciphertext,
            version,
            identity_only=args.identity_only,
            access_only=args.access_only,
        )
    print(json.dumps(report))


if __name__ == "__main__":
    try:
        main()
    except Exception:
        raise SystemExit("Validation failed; no credential details printed") from None
