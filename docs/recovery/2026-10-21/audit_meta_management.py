"""Exact staging WABA audit and one explicitly requested demo-template attempt.

Default performs GET reads after the existing guarded token introspection.
--create-demo can POST only the fixed payload below, to the fixed test WABA.
Never send messages, change callbacks, print credentials or follow paging URLs.
"""

import argparse
import json
import re
from datetime import UTC, datetime
from pathlib import Path

from connect_meta_test_webhook import (
    WABA_ID,
    credentials,
    graph_version,
    inspect_remote,
    new_client,
    snapshot,
)

DEMO_NAME = "luri_revision_solicitud_recibida_20261022"
DEMO_BODY = (
    "Confirmamos la recepción de tu solicitud de atención en Kalivur Marketing Pro. "
    "Un integrante del equipo te responderá por este canal."
)
DEMO = {
    "name": DEMO_NAME,
    "language": "es",
    "category": "UTILITY",
    "components": [{"type": "BODY", "text": DEMO_BODY}],
}
MARKER = Path("/tmp/luri-template-create-attempt-20261022.json")


def redact(value, secrets):
    if not isinstance(value, str):
        return None
    for secret in secrets:
        if secret:
            value = value.replace(secret, "[REDACTED]")
    value = re.sub(r"https?://\S+", "[URL omitted]", value)
    value = re.sub(r"EA[A-Za-z0-9]{20,}", "[REDACTED]", value)
    return value[:700]


def request(client, method, edge, secrets, *, params=None, payload=None):
    if edge not in {"", "/phone_numbers", "/message_templates"}:
        raise ValueError("unexpected edge")
    if method != "GET" and not (
        method == "POST" and edge == "/message_templates" and payload == DEMO
    ):
        raise ValueError("unexpected mutation")
    try:
        response = client.request(
            method,
            f"https://graph.facebook.com/{graph_version()}/{WABA_ID}{edge}",
            headers={"Authorization": f"Bearer {secrets[0]}"},
            params=params,
            json=payload,
            timeout=20.0,
        )
        result = {"http_status": response.status_code}
        if len(response.content) > 262_144:
            return None, {**result, "result": "response_too_large"}
        data = response.json()
        if not isinstance(data, dict):
            return None, {**result, "result": "unexpected_shape"}
        if response.status_code not in {200, 201} or "error" in data:
            error = data.get("error", {})
            if isinstance(error, dict):
                for key in ("code", "error_subcode"):
                    if type(error.get(key)) is int:
                        result[key] = error[key]
                for key in ("message", "error_user_title", "error_user_msg"):
                    safe = redact(error.get(key), secrets)
                    if safe:
                        result[key] = safe
            return None, {**result, "result": "provider_error"}
        return data, {**result, "result": "ok"}
    except Exception:
        return None, {"result": "request_failed_outcome_unknown_no_details"}


def template_summary(row):
    if not isinstance(row, dict):
        return {}
    safe = {}
    for key, pattern in (
        ("id", r"[0-9]{1,30}"),
        ("name", r"[a-z0-9_]{1,512}"),
        ("status", r"[A-Z_]{1,40}"),
        ("category", r"[A-Z_]{1,40}"),
        ("language", r"[A-Za-z_]{2,15}"),
    ):
        value = row.get(key)
        if isinstance(value, str) and re.fullmatch(pattern, value):
            safe[key] = value
    return safe


def exact_demo_rows(data):
    if not isinstance(data, dict) or not isinstance(data.get("data"), list):
        return None
    return [
        row
        for row in data["data"]
        if isinstance(row, dict) and row.get("name") == DEMO_NAME
    ]


def matches_demo(row):
    return (
        row.get("name") == DEMO_NAME
        and row.get("language") == DEMO["language"]
        and row.get("category") == DEMO["category"]
        and row.get("components") == DEMO["components"]
    )


def lookup_demo(client, secrets):
    return request(
        client,
        "GET",
        "/message_templates",
        secrets,
        params={
            "name": DEMO_NAME,
            "fields": "id,name,status,category,language,components",
            "limit": "25",
        },
    )


def create_demo(client, secrets, marker=MARKER):
    existing, lookup = lookup_demo(client, secrets)
    rows = exact_demo_rows(existing)
    if rows is None:
        return {"status": "lookup_failed_no_post", "lookup": lookup}
    if rows:
        return {
            "status": (
                "already_exists_no_post"
                if len(rows) == 1 and matches_demo(rows[0])
                else "name_collision_no_post"
            ),
            "existing": [template_summary(row) for row in rows],
        }
    try:
        with marker.open("x", encoding="utf8") as handle:
            json.dump(
                {
                    "waba_id": WABA_ID,
                    "name": DEMO_NAME,
                    "attempt_at_utc": datetime.now(UTC).isoformat(),
                },
                handle,
            )
    except FileExistsError:
        return {"status": "previous_attempt_recorded_no_post", "lookup": lookup}
    # At most one POST; do not retry on any transport or provider error.
    created, outcome = request(
        client, "POST", "/message_templates", secrets, payload=DEMO
    )
    readback, query = lookup_demo(client, secrets)
    rows = exact_demo_rows(readback)
    confirmed = rows is not None and len(rows) == 1 and matches_demo(rows[0])
    report = {
        "status": (
            "demo_created_and_readback_confirmed"
            if confirmed
            else "creation_not_confirmed_no_retry"
        ),
        "post": outcome,
        "returned": template_summary(created),
        "readback": query,
        "found": [template_summary(row) for row in rows] if rows is not None else [],
        "messages_sent": 0,
    }
    marker.write_text(json.dumps(report), encoding="utf8")
    return report


def audit(*, create=False):
    state = (
        snapshot()
    )  # Hard guards: exact private staging DB, tenant/bot, IA/off, transport disabled.
    remote = inspect_remote(state)  # DB transaction already closed.
    if not remote.get("ready_to_connect") or not remote.get("token", {}).get("passed"):
        return {"status": "preflight_failed_no_asset_requests", "preflight": remote}
    secrets = credentials(state)
    from demonstrate_meta_assets_read_only import exact_test_phone

    with new_client() as client:
        account, account_query = request(
            client, "GET", "", secrets, params={"fields": "id,name"}
        )
        phones, phones_query = request(
            client,
            "GET",
            "/phone_numbers",
            secrets,
            params={"fields": "id,display_phone_number", "limit": "25"},
        )
        templates, templates_query = request(
            client,
            "GET",
            "/message_templates",
            secrets,
            params={"fields": "id,name,status,category,language", "limit": "25"},
        )
        checks = {
            "account_id_matches": isinstance(account, dict)
            and account.get("id") == WABA_ID,
            "test_phone_matches": exact_test_phone(phones),
            "templates_readable": isinstance(templates, dict)
            and isinstance(templates.get("data"), list),
        }
        report = {
            "status": "management_read_audit_completed",
            "graph_api_version": graph_version(),
            "checks": checks,
            "queries": {
                "account": account_query,
                "phones": phones_query,
                "templates": templates_query,
            },
            "templates_first_page": (
                [template_summary(row) for row in templates["data"]]
                if checks["templates_readable"]
                else []
            ),
            "more_templates_not_followed": bool(
                templates and templates.get("paging", {}).get("next")
            ),
            "callback_matches": remote.get("subscription", {}).get(
                "override_matches_staging_test"
            ),
            "ai_enabled": False,
            "transport": "disabled",
            "messages_sent": 0,
            "creation": {"status": "not_requested"},
        }
        if create:
            report["creation"] = (
                create_demo(client, secrets)
                if all(checks.values())
                else {"status": "asset_checks_failed_no_post"}
            )
        return report


def main():
    parser = argparse.ArgumentParser(description=__doc__)
    parser.add_argument("--create-demo", action="store_true")
    parser.add_argument("--show-payload", action="store_true")
    args = parser.parse_args()
    print(
        json.dumps(
            DEMO if args.show_payload else audit(create=args.create_demo),
            ensure_ascii=True,
        )
    )


if __name__ == "__main__":
    try:
        main()
    except Exception:
        raise SystemExit("Audit incomplete; credential details omitted") from None
