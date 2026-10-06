"""Authenticated checks of customer workspace against a disposable localhost DB."""

import argparse
import json
from datetime import datetime
from pathlib import Path
from urllib.parse import urlsplit

import httpx


def main() -> None:
    parser = argparse.ArgumentParser(description=__doc__)
    parser.add_argument("--base-url", required=True)
    parser.add_argument("--manifest", type=Path, required=True)
    parser.add_argument("--output", type=Path, required=True)
    args = parser.parse_args()
    if urlsplit(args.base_url).hostname not in {"localhost", "127.0.0.1", "::1"}:
        parser.error("localhost only")
    manifest = json.loads(args.manifest.read_text(encoding="utf-8"))
    if manifest["environment"] != "disposable local PostgreSQL":
        parser.error("synthetic rehearsal only")
    org, other, contact, conversation = (
        manifest[k]
        for k in [
            "organization_id",
            "other_organization_id",
            "contact_id",
            "conversation_id",
        ]
    )
    results = []
    with httpx.Client(base_url=args.base_url, timeout=30) as client:
        base = f"/organizations/{org}/crm"
        assert client.get(f"{base}/customers/{contact}/workspace").status_code == 401
        assert client.get(f"{base}/commercial-report").status_code == 401
        for role, email in manifest["accounts"].items():
            login = client.post(
                "/auth/login", json={"email": email, "password": "SyntheticCRM2026!"}
            )
            assert login.status_code == 200
            headers = {"Authorization": "Bearer " + login.json()["access_token"]}
            own, foreign = (other, org) if role == "other_company" else (org, other)
            ownbase = f"/organizations/{own}/crm"
            assert (
                client.get(
                    f"/organizations/{foreign}/crm/commercial-report", headers=headers
                ).status_code
                == 403
            )
            assert (
                client.get(
                    f"/organizations/{foreign}/crm/customers/{contact}/workspace",
                    headers=headers,
                ).status_code
                == 403
            )
            if role == "other_company":
                assert (
                    client.get(f"{ownbase}/commercial-report", headers=headers).json()[
                        "items"
                    ]
                    == []
                )
                assert (
                    client.get(
                        f"{ownbase}/customers/{contact}/activities", headers=headers
                    ).status_code
                    == 404
                )
                results.append(
                    {"role": role, "foreign_denied": True, "own_report_empty": True}
                )
                continue
            for bucket in ("today", "future"):
                agenda = client.get(
                    f"{ownbase}/follow-up?due={bucket}", headers=headers
                )
                assert agenda.status_code == 200
                result = agenda.json()
                assert result["total"] == result["summary"][bucket]
                start = datetime.fromisoformat(result["day_start"])
                end = datetime.fromisoformat(result["day_end"])
                assert start < end
                for row in result["items"]:
                    assert row["stage_kind"] == "open" and row["next_action"]
                    date = datetime.fromisoformat(row["next_action"]["due_at"])
                    assert (start <= date < end) if bucket == "today" else date >= end
                    if role == "viewer":
                        assert (
                            row["next_action"]["description"] == "Contenido restringido"
                        )
                assert (
                    client.get(
                        f"/organizations/{foreign}/crm/follow-up?due={bucket}",
                        headers=headers,
                    ).status_code
                    == 403
                )
            if role == "organization_owner":
                me = client.get("/auth/me", headers=headers).json()["user"]
                payload = {
                    "title": "Oportunidad desde ficha por HTTP",
                    "contact_id": contact,
                    "stage_code": "new",
                    "assigned_user_id": me["id"],
                    "no_action_reason": "Esperar llamada",
                    "amount": "123.45",
                    "currency": "USD",
                }
                key = {**headers, "Idempotency-Key": "customer-http-op"}
                created = client.post(
                    f"{base}/opportunities", json=payload, headers=key
                )
                assert created.status_code == 201, created.text
                replay = client.post(f"{base}/opportunities", json=payload, headers=key)
                assert replay.json()["id"] == created.json()["id"]
            workspace = client.get(
                f"{base}/customers/{contact}/workspace", headers=headers
            )
            assert workspace.status_code == 200, workspace.text
            assert workspace.json()["opportunities"]["total"] >= 4
            action_history = client.get(
                f"{base}/customers/{contact}/action-history", headers=headers
            )
            assert action_history.status_code == 200
            assert any(
                row["status"] == "completed" for row in action_history.json()["items"]
            )
            if role == "viewer":
                assert all(
                    row["description"] == "Contenido restringido"
                    for row in action_history.json()["items"]
                )
            activity = {
                "kind": "note",
                "description": "Nota sintética HTTP recuperable",
                "occurred_at": "2026-10-05T15:00:00Z",
            }
            path = f"{base}/customers/{contact}/activities"
            key = {**headers, "Idempotency-Key": f"customer-http-{role}"}
            saved = client.post(path, json=activity, headers=key)
            if role == "viewer":
                assert saved.status_code == 403
                assert not workspace.json()["can_write"]
                assert all(
                    item["title"] == "Oportunidad"
                    for item in workspace.json()["opportunities"]["items"]
                )
                assert all(
                    item["description"] == "Contenido restringido"
                    for item in client.get(path, headers=headers).json()["items"]
                )
                assert (
                    client.get(
                        f"{base}/customers/{contact}/suggestions/{conversation}",
                        headers=headers,
                    ).status_code
                    == 403
                )
            else:
                assert saved.status_code == 201, saved.text
                assert (
                    client.post(path, json=activity, headers=key).json()["id"]
                    == saved.json()["id"]
                )
                assert (
                    client.post(
                        path,
                        json={**activity, "description": "Contenido distinto"},
                        headers=key,
                    ).status_code
                    == 409
                )
                suggestion = client.get(
                    f"{base}/customers/{contact}/suggestions/{conversation}",
                    headers=headers,
                )
                assert (
                    suggestion.status_code == 200 and not suggestion.json()["available"]
                )
            report = client.get(f"{base}/commercial-report", headers=headers)
            assert report.status_code == 200, report.text
            assert (
                sum(row["count"] for row in report.json()["items"])
                == client.get(f"{base}/opportunities", headers=headers).json()["total"]
            )
            if role == "viewer":
                assert all(
                    row["currency"] is None and row["amount"] is None
                    for row in report.json()["items"]
                )
            else:
                assert any(
                    row["currency"] == "USD" and row["amount"] == "123.45"
                    for row in report.json()["items"]
                )
            assert (
                client.get(
                    f"{base}/commercial-report",
                    params={"date_from": "2027-01-01T00:00:00Z"},
                    headers=headers,
                ).json()["items"]
                == []
            )
            results.append(
                {
                    "role": role,
                    "workspace": True,
                    "agenda_company_day_and_permissions": True,
                    "activities_deduplicated_or_write_denied": True,
                    "report_permissions": True,
                    "ai_disabled_abstains_or_denied": True,
                    "foreign_denied": True,
                }
            )
    args.output.write_text(
        json.dumps(
            {
                "environment": "authenticated localhost with PostgreSQL",
                "no_external_ai_calls": True,
                "roles": results,
            },
            indent=2,
        )
        + "\n",
        encoding="utf-8",
    )
    print("PASS authenticated customer workspace, journal, report and IA abstention")


if __name__ == "__main__":
    main()
